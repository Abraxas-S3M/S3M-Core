"""Stateful cursor over scenario packs for a training track.

Military/tactical context:
This cursor processes scenario packs in deterministic order to prevent replay
gaps after disrupted runs, preserving traceable adaptation chronology.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.training.cloud_cpu.contracts import DataClass, TrainerState, TrainingExample

logger = logging.getLogger("s3m.training.cloud_cpu.dataset_cursor")

_SCENARIO_DIR_RE = re.compile(r"^scenario-\d{5}$")


class DatasetCursor:
    """Iterates scenario packs and emits supervised micro-batches."""

    def __init__(
        self,
        track: str,
        scenarios_dir: Path,
        processed_dir: Path,
        rejected_dir: Path,
    ) -> None:
        self._track = str(track)
        self._scenarios_dir = Path(scenarios_dir)
        self._processed_dir = Path(processed_dir)
        self._rejected_dir = Path(rejected_dir)

        self._scenario_idx = 0
        self._line_idx = 0
        self._scenario_name: str = ""

        self._processed_dir.mkdir(parents=True, exist_ok=True)
        self._rejected_dir.mkdir(parents=True, exist_ok=True)

    def next_batch(self, batch_size: int) -> List[TrainingExample]:
        """Return next batch of examples, preserving cursor position."""
        if int(batch_size) <= 0:
            raise ValueError("batch_size must be > 0")

        examples: List[TrainingExample] = []
        remaining = int(batch_size)
        guard = 0
        while remaining > 0:
            guard += 1
            if guard > 10_000:
                raise RuntimeError("dataset cursor exceeded safety guard iterations")

            scenarios = self._discover_scenarios()
            if not scenarios:
                break
            scenario_idx = self._resolve_scenario_idx(scenarios)
            if scenario_idx >= len(scenarios):
                self._scenario_idx = len(scenarios)
                self._line_idx = 0
                self._scenario_name = ""
                break

            scenario_dir = scenarios[scenario_idx]
            read_result = self._read_examples(scenario_dir=scenario_dir, count=remaining)
            if read_result is None:
                self._reject_scenario(scenario_dir, reason="invalid scenario structure or checksum")
                self._line_idx = 0
                self._scenario_name = ""
                # Keep index; list shrinks after move.
                self._scenario_idx = scenario_idx
                continue

            from_scenario, exhausted = read_result
            examples.extend(from_scenario)
            remaining -= len(from_scenario)

            self._scenario_idx = scenario_idx
            self._scenario_name = scenario_dir.name
            if exhausted:
                self._complete_scenario(scenario_dir)
                self._line_idx = 0
                self._scenario_name = ""
                # Keep index; next scenario shifts into current slot.
                self._scenario_idx = scenario_idx
                continue

            if not from_scenario:
                break

        return examples

    def get_cursor(self) -> Dict[str, Any]:
        """Serializable cursor state for checkpoint persistence."""
        return {
            "scenario_idx": int(self._scenario_idx),
            "line_idx": int(self._line_idx),
            "scenario_name": self._scenario_name,
        }

    def save_to_state(self, state: TrainerState) -> None:
        """Persist cursor into TrainerState.dataset_cursor."""
        state.dataset_cursor = self.get_cursor()

    def restore_cursor(self, cursor_dict: Dict[str, Any]) -> None:
        """Restore cursor position from checkpoint payload."""
        self._scenario_idx = max(0, int(cursor_dict.get("scenario_idx", 0)))
        self._line_idx = max(0, int(cursor_dict.get("line_idx", 0)))
        self._scenario_name = str(cursor_dict.get("scenario_name", "") or "")

    def _discover_scenarios(self) -> List[Path]:
        if not self._scenarios_dir.exists():
            return []
        candidates = [
            path
            for path in sorted(self._scenarios_dir.iterdir(), key=lambda item: item.name)
            if path.is_dir() and _SCENARIO_DIR_RE.match(path.name) is not None
        ]
        return candidates

    def _resolve_scenario_idx(self, scenarios: List[Path]) -> int:
        if self._scenario_name:
            for idx, scenario in enumerate(scenarios):
                if scenario.name == self._scenario_name:
                    return idx
        return min(self._scenario_idx, len(scenarios))

    def _read_examples(self, scenario_dir: Path, count: int) -> Optional[Tuple[List[TrainingExample], bool]]:
        manifest_path = scenario_dir / "manifest.json"
        prompts_path = scenario_dir / "prompts.jsonl"
        labels_path = scenario_dir / "labels.jsonl"

        if not manifest_path.exists() or not prompts_path.exists() or not labels_path.exists():
            return None

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not self._is_manifest_valid(manifest=manifest, prompts_path=prompts_path, labels_path=labels_path):
            return None

        prompts_lines = prompts_path.read_text(encoding="utf-8").splitlines()
        labels_lines = labels_path.read_text(encoding="utf-8").splitlines()
        if len(prompts_lines) != len(labels_lines):
            return None

        if self._line_idx >= len(prompts_lines):
            return [], True

        data_class = self._parse_data_class(manifest.get("data_class", DataClass.COMMAND.value))
        scenario_id = str(manifest.get("scenario_id", scenario_dir.name))
        end = min(self._line_idx + max(1, int(count)), len(prompts_lines))

        rows: List[TrainingExample] = []
        for line_idx in range(self._line_idx, end):
            try:
                prompt_obj = json.loads(prompts_lines[line_idx])
                label_obj = json.loads(labels_lines[line_idx])
            except json.JSONDecodeError:
                return None

            prompt = self._extract_prompt(prompt_obj)
            completion = self._extract_completion(label_obj)
            if not prompt:
                return None

            weight = float(prompt_obj.get("weight", 1.0))
            if not math.isfinite(weight) or weight < 0.0:
                return None

            rows.append(
                TrainingExample(
                    prompt=prompt,
                    completion=completion,
                    domain_track=self._track,
                    data_class=data_class,
                    metadata={
                        "scenario_id": scenario_id,
                        "scenario_dir": scenario_dir.name,
                        "line_idx": line_idx,
                    },
                    weight=weight,
                )
            )

        self._line_idx = end
        exhausted = self._line_idx >= len(prompts_lines)
        return rows, exhausted

    def _is_manifest_valid(self, manifest: Dict[str, Any], prompts_path: Path, labels_path: Path) -> bool:
        track_value = str(manifest.get("track", self._track))
        if track_value != self._track:
            return False

        expected_prompts_sha = self._extract_checksum(manifest, "prompts.jsonl")
        expected_labels_sha = self._extract_checksum(manifest, "labels.jsonl")
        if not expected_prompts_sha or not expected_labels_sha:
            return False

        actual_prompts_sha = self._sha256_file(prompts_path)
        actual_labels_sha = self._sha256_file(labels_path)
        return (
            actual_prompts_sha.lower() == expected_prompts_sha.lower()
            and actual_labels_sha.lower() == expected_labels_sha.lower()
        )

    @staticmethod
    def _extract_checksum(manifest: Dict[str, Any], filename: str) -> str:
        checksums = manifest.get("checksums", {})
        if isinstance(checksums, dict):
            value = checksums.get(filename)
            if isinstance(value, str) and value.strip():
                return value.strip()

        prefix = filename.split(".")[0]
        for key in (f"{prefix}_sha256", f"{prefix}_checksum", f"{filename}_sha256"):
            value = manifest.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_prompt(payload: Dict[str, Any]) -> str:
        for key in ("prompt", "instruction", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_completion(payload: Dict[str, Any]) -> str:
        for key in ("completion", "output", "response", "label"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return ""

    @staticmethod
    def _parse_data_class(value: Any) -> DataClass:
        try:
            return DataClass(str(value))
        except ValueError:
            return DataClass.COMMAND

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        return hasher.hexdigest()

    def _complete_scenario(self, scenario_dir: Path) -> None:
        destination = self._destination_path(self._processed_dir, scenario_dir.name)
        shutil.move(str(scenario_dir), str(destination))
        logger.info("Scenario completed and moved to processed: %s", destination.name)

    def _reject_scenario(self, scenario_dir: Path, reason: str) -> None:
        destination = self._destination_path(self._rejected_dir, scenario_dir.name)
        shutil.move(str(scenario_dir), str(destination))
        logger.warning("Scenario rejected (%s): %s", reason, destination.name)

    @staticmethod
    def _destination_path(parent: Path, base_name: str) -> Path:
        candidate = parent / base_name
        if not candidate.exists():
            return candidate
        suffix = 1
        while True:
            candidate = parent / f"{base_name}-{suffix:03d}"
            if not candidate.exists():
                return candidate
            suffix += 1

