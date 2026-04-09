#!/usr/bin/env python3
"""Periodic BackBlaze B2 synchronization for Hetzner cloud CPU training.

Military/tactical context:
This daemon keeps cloud-side adaptation nodes supplied with approved data while
pushing training telemetry and checkpoints back to the sovereign vault so
operators retain continuity during degraded or disrupted connectivity.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.storage.b2_connector import B2Connector
from src.storage.vault_paths import VaultPaths

LOGGER = logging.getLogger("s3m.infra.b2_sync")


class B2SyncDaemon:
    """Periodic bidirectional sync between Hetzner and BackBlaze B2."""

    def __init__(self, config_path: str = "configs/deployment/backblaze.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        self.sync_cfg = self.config.get("sync", {}) if isinstance(self.config.get("sync"), dict) else {}

        self.tracks = self._string_list(self.sync_cfg.get("tracks"), default=["saudi_mod", "ukraine_mod", "nato"])
        self.quantized_pull_engines = self._string_list(
            self.sync_cfg.get("quantized_pull_engines"),
            default=["phi3-medium", "mistral-7b"],
        )
        self.adapters_engine_ids = self._string_list(
            self.sync_cfg.get("adapters_engine_ids"),
            default=["phi3-medium", "mistral-7b"],
        )
        self.engines_blocked_from_pull = self._string_list(
            self.sync_cfg.get("engines_blocked_from_pull"),
            default=["grok", "grok-300b", "base-weights/grok-300b", "quantized/grok-300b"],
        )

        self.local_cfg = self.sync_cfg.get("local", {}) if isinstance(self.sync_cfg.get("local"), dict) else {}
        self.training_root = Path(
            str(self.local_cfg.get("training_root", "/opt/s3m/state/training/cloud_cpu"))
        ).resolve()
        self.models_root = Path(str(self.local_cfg.get("models_root", "/opt/s3m/models"))).resolve()
        self.adapters_root = Path(str(self.local_cfg.get("adapters_root", "/opt/s3m/adapters"))).resolve()
        self.metrics_root = Path(
            str(self.local_cfg.get("metrics_root", "/opt/s3m/state/training/cloud_cpu/metrics"))
        ).resolve()
        self.gui_snapshots_root = Path(str(self.local_cfg.get("gui_snapshots_root", "/opt/s3m/gui-snapshots"))).resolve()

        self.node_id = str(self.sync_cfg.get("node_id", "hetzner")).strip() or "hetzner"
        self.connector = B2Connector.from_config(self.config)

        self._ensure_local_layout()

    def sync_cycle(self) -> dict[str, int]:
        """One complete sync cycle — called every N minutes."""
        totals = {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        # PULL 1) Scenario packs for all training tracks.
        for track in self.tracks:
            remote_prefix = VaultPaths.dataset_scenarios(track)
            local_dir = self.training_root / "tracks" / track / "scenarios"
            self._accumulate(totals, self._pull_prefix(remote_prefix, local_dir))

        # PULL 2) Approved quantized weights only (phi + mistral).
        for engine_id in self.quantized_pull_engines:
            remote_prefix = VaultPaths.quantized_engine(engine_id)
            local_dir = self.models_root / engine_id
            self._accumulate(totals, self._pull_prefix(remote_prefix, local_dir))

        # PULL 3) Latest promoted adapters per engine/track.
        for engine_id in self.adapters_engine_ids:
            for track in self.tracks:
                remote_prefix = VaultPaths.adapters(engine_id, track=track)
                local_dir = self.adapters_root / engine_id / track
                self._accumulate(totals, self._pull_prefix(remote_prefix, local_dir))

        # PUSH 4) Track checkpoints back to vault.
        for track in self.tracks:
            local_dir = self.training_root / "tracks" / track / "checkpoints"
            remote_prefix = VaultPaths.checkpoints(self.node_id, track=track)
            self._accumulate(totals, self._push_prefix(local_dir, remote_prefix))

        # PUSH 5) Evaluation/metrics payloads.
        self._accumulate(totals, self._push_prefix(self.metrics_root, VaultPaths.eval_results(self.node_id)))

        # PUSH 6) GUI snapshots for operator visibility.
        self._accumulate(totals, self._push_prefix(self.gui_snapshots_root, VaultPaths.gui_snapshots()))

        LOGGER.info("Sync cycle complete: %s", totals)
        return totals

    def run_forever(self, interval_minutes: int = 30) -> None:
        """Main loop — sync every interval_minutes."""
        interval = max(1, int(interval_minutes))
        LOGGER.info("Starting B2 sync daemon loop (interval=%s minutes)", interval)
        while True:
            started = time.monotonic()
            try:
                self.sync_cycle()
            except Exception:  # pragma: no cover - service uptime guard
                LOGGER.exception("Sync cycle failed")
            elapsed = time.monotonic() - started
            sleep_seconds = max(0.0, (interval * 60) - elapsed)
            time.sleep(sleep_seconds)

    def _pull_prefix(self, remote_prefix: str, local_dir: Path) -> dict[str, int]:
        prefix = self._normalize_prefix(remote_prefix)
        if not self._pull_allowed(prefix):
            LOGGER.warning("Blocked pull prefix encountered: %s", prefix)
            return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        blocked_tokens = ["grok", *self.engines_blocked_from_pull]
        list_objects = getattr(self.connector, "list_objects", None)
        if callable(list_objects):
            for entry in list_objects(prefix):
                key = str(entry.get("Key", ""))
                if key and (("grok" in key.lower()) or VaultPaths.contains_blocked_token(key, blocked_tokens)):
                    LOGGER.warning("Blocked pull key encountered: %s", key)
                    return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        local_dir.mkdir(parents=True, exist_ok=True)
        result = self.connector.sync_prefix_to_local(prefix=prefix, local_dir=local_dir, blocked_tokens=blocked_tokens)
        LOGGER.info("Pull sync %s -> %s :: %s", prefix, local_dir, result)
        return self._normalize_result(result)

    def _push_prefix(self, local_dir: Path, remote_prefix: str) -> dict[str, int]:
        prefix = self._normalize_prefix(remote_prefix)
        if not local_dir.exists():
            LOGGER.info("Push source missing, skipping: %s", local_dir)
            return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        result = self.connector.sync_local_to_prefix(local_dir=local_dir, prefix=prefix)
        LOGGER.info("Push sync %s -> %s :: %s", local_dir, prefix, result)
        return self._normalize_result(result)

    def _pull_allowed(self, remote_prefix: str) -> bool:
        lowered = remote_prefix.lower()
        if "grok" in lowered:
            return False
        if VaultPaths.contains_blocked_token(remote_prefix, self.engines_blocked_from_pull):
            return False
        return True

    def _ensure_local_layout(self) -> None:
        self.models_root.mkdir(parents=True, exist_ok=True)
        self.adapters_root.mkdir(parents=True, exist_ok=True)
        self.metrics_root.mkdir(parents=True, exist_ok=True)
        self.gui_snapshots_root.mkdir(parents=True, exist_ok=True)
        for track in self.tracks:
            (self.training_root / "tracks" / track / "scenarios").mkdir(parents=True, exist_ok=True)
            (self.training_root / "tracks" / track / "checkpoints").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        text = str(prefix or "").strip().lstrip("/")
        if ".." in text:
            raise ValueError("sync prefix contains unsupported traversal token")
        if text and not text.endswith("/"):
            text += "/"
        return text

    @staticmethod
    def _normalize_result(result: dict[str, Any]) -> dict[str, int]:
        payload = dict(result or {})
        return {
            "downloaded": int(payload.get("downloaded", 0)),
            "uploaded": int(payload.get("uploaded", 0)),
            "skipped": int(payload.get("skipped", 0)),
            "bytes_transferred": int(payload.get("bytes_transferred", 0)),
        }

    @staticmethod
    def _accumulate(total: dict[str, int], delta: dict[str, int]) -> None:
        for key in ("downloaded", "uploaded", "skipped", "bytes_transferred"):
            total[key] = int(total.get(key, 0)) + int(delta.get(key, 0))

    @staticmethod
    def _string_list(value: Any, default: list[str]) -> list[str]:
        if not isinstance(value, list):
            return list(default)
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result or list(default)

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"B2 sync config not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("B2 sync config must be a mapping")
        return raw


def _configure_logging() -> None:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="S3M BackBlaze B2 sync daemon")
    parser.add_argument("--config", default="configs/deployment/backblaze.yaml", help="Path to sync config file")
    parser.add_argument("--once", action="store_true", help="Run exactly one sync cycle and exit")
    parser.add_argument("--interval-minutes", type=int, default=0, help="Run interval for daemon loop")
    return parser.parse_args()


def main() -> int:
    _configure_logging()
    args = _parse_args()
    daemon = B2SyncDaemon(config_path=str(args.config))
    if args.once:
        daemon.sync_cycle()
        return 0
    configured_interval = int(daemon.sync_cfg.get("interval_minutes", 30))
    daemon.run_forever(interval_minutes=args.interval_minutes or configured_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
