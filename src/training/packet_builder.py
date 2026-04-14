"""Scenario-pack builder for cloud CPU tactical training queues.

Military/tactical context:
This builder transforms raw supervision into tamper-evident scenario packets so
contested-network retraining pipelines can ingest trusted, resumable data slices.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_SCENARIO_DIR_RE = re.compile(r"^scenario-(\d{5})$")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_ENGLISH_RE = re.compile(r"[A-Za-z]")

_ALLOWED_TRACKS = {"saudi_mod", "ukraine_mod", "nato", "shared"}
_ALLOWED_DATA_CLASSES = {"command", "cop_intel", "risk_readiness", "bilingual"}
_ALLOWED_SOURCES = {"manual", "claude_generated", "synthetic"}


def _load_contract_data_class_values() -> Dict[str, str]:
    """Resolve canonical DataClass values without assuming package __init__ health."""
    try:
        from src.training.cloud_cpu.contracts import DataClass  # type: ignore

        return {
            "command": DataClass.COMMAND.value,
            "cop_intel": DataClass.INTELLIGENCE.value,
            "risk_readiness": DataClass.SAFETY.value,
            "bilingual": DataClass.INTELLIGENCE.value,
        }
    except Exception:
        contracts_path = Path(__file__).resolve().parent / "cloud_cpu" / "contracts.py"
        spec = importlib.util.spec_from_file_location("s3m_contracts_fallback", contracts_path)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            enum_obj = getattr(module, "DataClass", None)
            if enum_obj is not None:
                return {
                    "command": str(enum_obj.COMMAND.value),
                    "cop_intel": str(enum_obj.INTELLIGENCE.value),
                    "risk_readiness": str(enum_obj.SAFETY.value),
                    "bilingual": str(enum_obj.INTELLIGENCE.value),
                }
        return {
            "command": "command",
            "cop_intel": "intelligence",
            "risk_readiness": "safety",
            "bilingual": "intelligence",
        }


_DATA_CLASS_TO_CONTRACT = _load_contract_data_class_values()


class PacketBuilder:
    """Build scenario packs from raw JSONL training data."""

    def __init__(self, source: str = "manual") -> None:
        self._source = self._validate_source(source)

    def build_from_jsonl(
        self,
        input_file: Path,
        track: str,
        data_class: str,
        output_dir: Path,
        examples_per_pack: int = 50,
    ) -> List[Path]:
        """Split input into numbered scenario packs with checksums."""
        input_file = Path(input_file)
        output_dir = Path(output_dir)
        self._validate_track(track)
        self._validate_data_class(data_class)

        if not input_file.exists() or not input_file.is_file():
            raise FileNotFoundError(f"Input JSONL file not found: {input_file}")
        if int(examples_per_pack) <= 0:
            raise ValueError("examples_per_pack must be > 0")

        pairs: List[Dict[str, str]] = []
        with input_file.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
                pairs.append(self._normalize_raw_payload(payload, line_number=line_number))

        if not pairs:
            return []

        output_dir.mkdir(parents=True, exist_ok=True)
        next_scenario_id = self._next_available_scenario_id(output_dir)
        built_packs: List[Path] = []
        for offset in range(0, len(pairs), int(examples_per_pack)):
            chunk = pairs[offset : offset + int(examples_per_pack)]
            scenario_id = next_scenario_id + (offset // int(examples_per_pack))
            built_packs.extend(
                self.build_from_pairs(
                    pairs=chunk,
                    track=track,
                    data_class=data_class,
                    output_dir=output_dir,
                    scenario_id_start=scenario_id,
                )
            )
        return built_packs

    def build_from_pairs(
        self,
        pairs: List[Dict[str, str]],
        track: str,
        data_class: str,
        output_dir: Path,
        scenario_id_start: int = 1,
    ) -> List[Path]:
        """Build scenario packs from in-memory prompt/completion pairs."""
        output_dir = Path(output_dir)
        self._validate_track(track)
        self._validate_data_class(data_class)
        if int(scenario_id_start) <= 0:
            raise ValueError("scenario_id_start must be >= 1")
        if not pairs:
            return []

        normalized_pairs: List[Dict[str, str]] = []
        for index, pair in enumerate(pairs, start=1):
            if not isinstance(pair, dict):
                raise ValueError(f"Pair #{index} must be an object")
            prompt = pair.get("prompt")
            completion = pair.get("completion")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"Pair #{index} has empty or invalid prompt")
            if not isinstance(completion, str):
                raise ValueError(f"Pair #{index} has invalid completion")
            normalized_pairs.append({"prompt": prompt.strip(), "completion": completion})

        scenario_id = f"scenario-{int(scenario_id_start):05d}"
        pack_dir = output_dir / scenario_id
        if pack_dir.exists():
            raise FileExistsError(f"Scenario directory already exists: {pack_dir}")
        pack_dir.mkdir(parents=True, exist_ok=False)

        prompts_path = pack_dir / "prompts.jsonl"
        labels_path = pack_dir / "labels.jsonl"

        with prompts_path.open("w", encoding="utf-8") as prompts_handle, labels_path.open(
            "w", encoding="utf-8"
        ) as labels_handle:
            for pair in normalized_pairs:
                prompts_handle.write(json.dumps({"prompt": pair["prompt"], "weight": 1.0}, ensure_ascii=False))
                prompts_handle.write("\n")
                labels_handle.write(json.dumps({"completion": pair["completion"]}, ensure_ascii=False))
                labels_handle.write("\n")

        manifest = {
            "scenario_id": scenario_id,
            "track": track,
            "data_class": data_class,
            "example_count": len(normalized_pairs),
            "language": self._detect_language([pair["prompt"] for pair in normalized_pairs]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": self._source,
            "checksums": {
                "prompts.jsonl": self._sha256_file(prompts_path),
                "labels.jsonl": self._sha256_file(labels_path),
            },
        }
        (pack_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [pack_dir]

    def validate_pack(self, pack_dir: Path) -> bool:
        """Validate a scenario pack has correct structure and checksums."""
        pack_dir = Path(pack_dir)
        match = _SCENARIO_DIR_RE.match(pack_dir.name)
        if match is None or not pack_dir.is_dir():
            return False

        manifest_path = pack_dir / "manifest.json"
        prompts_path = pack_dir / "prompts.jsonl"
        labels_path = pack_dir / "labels.jsonl"
        if not manifest_path.exists() or not prompts_path.exists() or not labels_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        if not isinstance(manifest, dict):
            return False

        try:
            self._validate_track(str(manifest.get("track", "")))
            self._validate_data_class(str(manifest.get("data_class", "")))
        except ValueError:
            return False

        if str(manifest.get("scenario_id", "")) != pack_dir.name:
            return False

        checksums = manifest.get("checksums")
        if not isinstance(checksums, dict):
            return False
        expected_prompts_sha = checksums.get("prompts.jsonl")
        expected_labels_sha = checksums.get("labels.jsonl")
        if not isinstance(expected_prompts_sha, str) or not expected_prompts_sha.strip():
            return False
        if not isinstance(expected_labels_sha, str) or not expected_labels_sha.strip():
            return False

        try:
            prompt_lines = prompts_path.read_text(encoding="utf-8").splitlines()
            label_lines = labels_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False

        if len(prompt_lines) != len(label_lines):
            return False

        for line in prompt_lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return False
            if not isinstance(payload, dict):
                return False
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                return False

        actual_prompts_sha = self._sha256_file(prompts_path)
        actual_labels_sha = self._sha256_file(labels_path)
        if actual_prompts_sha.lower() != expected_prompts_sha.lower():
            return False
        if actual_labels_sha.lower() != expected_labels_sha.lower():
            return False
        return True

    def upload_packs(self, pack_dirs: List[Path], track: str) -> List[str]:
        """Upload validated packs to Cloudflare R2 under datasets/{track}/scenarios/."""
        self._validate_track(track)
        uploaded_prefixes: List[str] = []
        for raw_dir in pack_dirs:
            pack_dir = Path(raw_dir)
            if not self.validate_pack(pack_dir):
                raise ValueError(f"Refusing to upload invalid packet: {pack_dir}")

            manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest_track = str(manifest.get("track", ""))
            if manifest_track != track:
                raise ValueError(
                    f"Packet track mismatch for {pack_dir.name}: manifest={manifest_track}, requested={track}"
                )

            remote_prefix = f"datasets/{track}/scenarios/{pack_dir.name}"
            for file_name in ("manifest.json", "prompts.jsonl", "labels.jsonl"):
                local_path = pack_dir / file_name
                remote_key = f"{remote_prefix}/{file_name}"
                self._upload_file(local_path=local_path, remote_key=remote_key)
            uploaded_prefixes.append(remote_prefix)
        return uploaded_prefixes

    def _normalize_raw_payload(self, payload: Any, line_number: int) -> Dict[str, str]:
        if not isinstance(payload, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object")

        candidate_pairs = (
            ("prompt", "completion"),
            ("instruction", "output"),
            ("input", "response"),
        )
        prompt_value: Any = None
        completion_value: Any = None
        for prompt_key, completion_key in candidate_pairs:
            if prompt_key in payload or completion_key in payload:
                prompt_value = payload.get(prompt_key)
                completion_value = payload.get(completion_key)
                break

        if not isinstance(prompt_value, str) or not prompt_value.strip():
            raise ValueError(f"Line {line_number} has empty or invalid prompt text")
        if not isinstance(completion_value, str):
            raise ValueError(f"Line {line_number} has invalid completion text")
        return {"prompt": prompt_value.strip(), "completion": completion_value}

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        return hasher.hexdigest()

    @staticmethod
    def _next_available_scenario_id(output_dir: Path) -> int:
        if not output_dir.exists():
            return 1
        max_id = 0
        for child in output_dir.iterdir():
            if not child.is_dir():
                continue
            match = _SCENARIO_DIR_RE.match(child.name)
            if match is None:
                continue
            max_id = max(max_id, int(match.group(1)))
        return max_id + 1

    @staticmethod
    def _detect_language(prompts: List[str]) -> str:
        has_arabic = any(_ARABIC_RE.search(prompt) is not None for prompt in prompts)
        has_english = any(_ENGLISH_RE.search(prompt) is not None for prompt in prompts)
        if has_arabic and has_english:
            return "bilingual"
        if has_arabic:
            return "ar"
        return "en"

    @staticmethod
    def _validate_track(track: str) -> None:
        normalized = str(track).strip()
        if normalized not in _ALLOWED_TRACKS:
            allowed = ", ".join(sorted(_ALLOWED_TRACKS))
            raise ValueError(f"Unsupported track '{track}'. Allowed tracks: {allowed}")

    @staticmethod
    def _validate_data_class(data_class: str) -> str:
        normalized = str(data_class).strip()
        if normalized not in _ALLOWED_DATA_CLASSES:
            allowed = ", ".join(sorted(_ALLOWED_DATA_CLASSES))
            raise ValueError(f"Unsupported data_class '{data_class}'. Allowed values: {allowed}")
        return _DATA_CLASS_TO_CONTRACT[normalized]

    @staticmethod
    def _validate_source(source: str) -> str:
        normalized = str(source).strip()
        if normalized not in _ALLOWED_SOURCES:
            allowed = ", ".join(sorted(_ALLOWED_SOURCES))
            raise ValueError(f"Unsupported source '{source}'. Allowed values: {allowed}")
        return normalized

    @staticmethod
    def _upload_file_with_object_storage_connector(connector: Any, local_path: Path, remote_key: str) -> bool:
        methods = ("upload_file", "upload_path", "upload")
        for method_name in methods:
            method = getattr(connector, method_name, None)
            if method is None:
                continue

            attempts = [
                lambda: method(local_path=local_path, remote_key=remote_key),
                lambda: method(local_path=str(local_path), remote_key=remote_key),
                lambda: method(file_path=str(local_path), remote_key=remote_key),
                lambda: method(local_path=str(local_path), object_key=remote_key),
                lambda: method(str(local_path), remote_key),
            ]
            for attempt in attempts:
                try:
                    attempt()
                    return True
                except TypeError:
                    continue
        return False

    def _upload_file(self, local_path: Path, remote_key: str) -> None:
        try:
            from src.storage.object_storage import ObjectStorageConnector  # type: ignore
        except Exception:
            ObjectStorageConnector = None

        if ObjectStorageConnector is not None:
            connector = ObjectStorageConnector()
            if self._upload_file_with_object_storage_connector(connector, local_path=local_path, remote_key=remote_key):
                return

        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for object storage upload when src.storage.object_storage is unavailable"
            ) from exc

        bucket = os.getenv("S3M_STORAGE_BUCKET_NAME", "").strip()
        key_id = os.getenv("S3M_STORAGE_ACCESS_KEY", "").strip()
        application_key = os.getenv("S3M_STORAGE_SECRET_KEY", "").strip()
        endpoint_url = os.getenv("S3M_STORAGE_ENDPOINT", "").strip() or None
        if not bucket or not key_id or not application_key:
            raise RuntimeError(
                "Missing object storage credentials; set S3M_STORAGE_BUCKET_NAME, "
                "S3M_STORAGE_ACCESS_KEY, S3M_STORAGE_SECRET_KEY, and S3M_STORAGE_ENDPOINT."
            )

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=key_id,
            aws_secret_access_key=application_key,
        )
        client.upload_file(str(local_path), bucket, remote_key)

