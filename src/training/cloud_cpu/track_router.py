"""Routes incoming scenario packs from inbox/ into track queues.

Military/tactical context:
Strict pre-routing validation blocks malformed or spoofed packs from entering
active adaptation queues, reducing adversarial data poisoning risk.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Dict

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack

logger = logging.getLogger("s3m.training.cloud_cpu.track_router")

_SCENARIO_DIR_RE = re.compile(r"^scenario-\d{5}$")


class TrackRouter:
    """Validates and routes scenario packs to per-track scenario directories."""

    def __init__(self, paths: StatePaths) -> None:
        self._paths = paths

    def route_inbox(self) -> Dict[str, int]:
        counts: Dict[str, int] = {track.value: 0 for track in TrainingTrack}
        inbox = self._paths.inbox
        if not inbox.exists():
            return counts

        for pack_dir in sorted(inbox.iterdir(), key=lambda item: item.name):
            if not pack_dir.is_dir():
                continue
            if _SCENARIO_DIR_RE.match(pack_dir.name) is None:
                self._reject(pack_dir, "invalid scenario directory name")
                continue

            manifest = self._load_manifest(pack_dir)
            if manifest is None:
                self._reject(pack_dir, "missing or malformed manifest")
                continue

            track_raw = str(manifest.get("track", "")).strip()
            try:
                track = TrainingTrack(track_raw)
            except ValueError:
                self._reject(pack_dir, f"unknown track '{track_raw}'")
                continue

            if not self._valid_structure(pack_dir):
                self._reject(pack_dir, "missing required prompts/labels payload files")
                continue

            destination_parent = self._paths.scenario_dir(track)
            destination = self._dedup_destination(destination_parent, pack_dir.name)
            shutil.move(str(pack_dir), str(destination))
            counts[track.value] += 1
            logger.info("Routed scenario pack %s -> %s", destination.name, track.value)

        return counts

    @staticmethod
    def _load_manifest(pack_dir: Path) -> Dict[str, object] | None:
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _valid_structure(pack_dir: Path) -> bool:
        return (pack_dir / "prompts.jsonl").exists() and (pack_dir / "labels.jsonl").exists()

    def _reject(self, pack_dir: Path, reason: str) -> None:
        rejected_root = self._paths.rejected / "inbox"
        rejected_root.mkdir(parents=True, exist_ok=True)
        destination = self._dedup_destination(rejected_root, pack_dir.name)
        shutil.move(str(pack_dir), str(destination))
        logger.warning("Rejected scenario pack %s (%s)", destination.name, reason)

    @staticmethod
    def _dedup_destination(parent: Path, base_name: str) -> Path:
        candidate = parent / base_name
        if not candidate.exists():
            return candidate
        suffix = 1
        while True:
            candidate = parent / f"{base_name}-{suffix:03d}"
            if not candidate.exists():
                return candidate
            suffix += 1

