"""Distributed weight synchronization manager for the 3-tier training topology.

Tactical context:
    Reliable movement of base, quantized, and adapter artifacts between cloud
    and vault tiers preserves mission readiness when edge teams must rebuild
    local runtimes without internet dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from src.storage.b2_connector import B2Connector
from src.storage.precision_manager import PrecisionManager
from src.storage.vault_paths import VaultPaths

logger = logging.getLogger("s3m.distributed.sync")


class SyncManager:
    """Sovereign vault sync operations via S3-compatible Object Storage.

    Military/tactical context:
    This manager coordinates artifact flow between edge nodes and the
    sovereign vault using the S3 protocol, eliminating SSH/rsync
    dependency for contested-network resilience.
    """

    _ENGINE_ALIASES = {
        "phi3_medium": {"phi3", "phi3_medium", "phi3-medium", "PHI3", "PHI3_MEDIUM"},
        "grok1": {"grok", "grok1", "grok-1", "GROK", "GROK1"},
        "mixtral": {"mistral", "mixtral", "MISTRAL", "MIXTRAL"},
        "allam": {"allam", "ALLAM"},
    }
    _VALID_CONTENT = {"base", "quantized", "adapters"}
    _ENGINE_METADATA = {
        "phi3_medium": {
            "hf_pull": (
                "huggingface-cli download microsoft/Phi-3-medium-4k-instruct "
                "--local-dir models/phi3-medium/"
            ),
            "fp16_gb": 14.0,
        },
        "grok1": {
            "hf_pull": (
                "huggingface-cli download xai-org/grok-1 --repo-type model "
                "--include 'ckpt-0/*' --local-dir models/grok1/"
            ),
            "fp16_gb": 650.0,
        },
        "mixtral": {
            "hf_pull": (
                "huggingface-cli download mistralai/Mixtral-8x7B-Instruct-v0.1 "
                "--local-dir models/mixtral/"
            ),
            "fp16_gb": 90.0,
        },
        "allam": {
            "hf_pull": (
                "huggingface-cli download humain-ai/ALLaM-7B-Instruct-preview "
                "--local-dir models/allam/"
            ),
            "fp16_gb": 14.0,
        },
    }

    def __init__(self, config_path: str = "configs/distributed_training.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        distributed = self.config.get("distributed_training", self.config)
        self.tracks = self._resolve_tracks(distributed)
        self.engine_ids = self._resolve_engines(distributed)
        self.connector = B2Connector()

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        if not config_path.exists():
            logger.warning("Distributed config not found: %s", config_path)
            return {}
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return payload if isinstance(payload, dict) else {}

    def _resolve_tracks(self, distributed: Dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        for key in ("tracks", "training_tracks"):
            value = distributed.get(key)
            if isinstance(value, list):
                candidates.extend(str(item).strip() for item in value if str(item).strip())
        if not candidates:
            candidates = ["saudi_mod", "ukraine_mod", "nato"]
        return candidates

    def _resolve_engines(self, distributed: Dict[str, Any]) -> list[str]:
        profile_block = distributed.get("training_profiles")
        if isinstance(profile_block, dict):
            engines = [str(key).strip() for key in profile_block if str(key).strip()]
            if engines:
                return engines
        return list(self._ENGINE_METADATA.keys())

    def _canonical_engine(self, engine: str) -> str:
        if not isinstance(engine, str) or not engine.strip():
            raise ValueError("engine must be a non-empty string")
        raw = engine.strip()
        for canonical, aliases in self._ENGINE_ALIASES.items():
            if raw in aliases:
                return canonical
        raise ValueError(f"Unsupported engine identifier: {engine}")

    def _validate_content(self, content: str) -> str:
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        normalized = content.strip().lower()
        if normalized not in self._VALID_CONTENT:
            raise ValueError(f"content must be one of {sorted(self._VALID_CONTENT)}")
        return normalized

    @staticmethod
    def _bytes_from_result(result: Any, transfer_kind: str) -> int:
        if isinstance(result, dict):
            if "bytes" in result:
                return int(result.get("bytes", 0))
            if "bytes_transferred" in result:
                return int(result.get("bytes_transferred", 0))
            if transfer_kind == "upload":
                return int(result.get("uploaded", 0))
            if transfer_kind == "download":
                return int(result.get("downloaded", 0))
        if isinstance(result, list):
            return len(result)
        return 0

    def _remote_prefix(self, engine: str, content: str) -> str:
        if content == "base":
            return VaultPaths.fp16_base(engine)
        if content == "quantized":
            return VaultPaths.q4_serving(engine)
        return VaultPaths.adapters(engine)

    def pull_from_vault(self, engine: str, target_dir: str, content: str = "base") -> dict[str, Any]:
        """Pull artifacts from Object Storage vault."""
        engine_key = self._canonical_engine(engine)
        content_key = self._validate_content(content)
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)
        remote = self._remote_prefix(engine_key, content_key)

        try:
            result = self.connector.sync_down(remote, target_path)
            return {
                "status": "ok",
                "engine": engine_key,
                "bytes_transferred": self._bytes_from_result(result, "download"),
            }
        except Exception as exc:
            logger.error("Vault pull failed engine=%s content=%s err=%s", engine_key, content_key, exc)
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

    def push_to_vault(self, engine: str, source_dir: str, content: str = "adapters") -> dict[str, Any]:
        """Push artifacts to Object Storage vault."""
        engine_key = self._canonical_engine(engine)
        content_key = self._validate_content(content)
        source_path = Path(source_dir)
        if not source_path.exists():
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        remote = self._remote_prefix(engine_key, content_key)
        try:
            if source_path.is_file():
                self.connector.upload_file(source_path, f"{remote}{source_path.name}")
                transferred = int(source_path.stat().st_size)
            else:
                result = self.connector.sync_up(source_path, remote)
                transferred = self._bytes_from_result(result, "upload")
            return {"status": "ok", "engine": engine_key, "bytes_transferred": transferred}
        except Exception as exc:
            logger.error("Vault push failed engine=%s content=%s err=%s", engine_key, content_key, exc)
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

    def check_vault_status(self) -> dict[str, dict[str, Any]]:
        """Query vault inventory via Object Storage API."""
        pm = PrecisionManager(self.connector)
        return pm.get_model_inventory()

    def get_engine_weight_status(self) -> dict[str, dict[str, bool]]:
        """Determine per-engine base/quantized/adapters availability on vault."""
        status: Dict[str, Dict[str, bool]] = {}
        for engine in self._ENGINE_METADATA:
            status[engine] = {
                "base": bool(self.connector.list_keys(VaultPaths.fp16_base(engine))),
                "quantized": bool(self.connector.list_keys(VaultPaths.q4_serving(engine))),
                "adapters": bool(self.connector.list_keys(VaultPaths.adapters(engine))),
            }
        return status

    def generate_pull_commands(self) -> dict[str, str]:
        """Return Hugging Face pull commands for all engines."""
        return {engine: metadata["hf_pull"] for engine, metadata in self._ENGINE_METADATA.items()}

    def estimate_download_time(self, bandwidth_mbps: float = 100) -> dict[str, dict[str, float]]:
        """Estimate fp16 download durations for each engine at given bandwidth."""
        if bandwidth_mbps <= 0:
            raise ValueError("bandwidth_mbps must be positive")

        estimates: dict[str, dict[str, float]] = {}
        total_seconds = 0.0
        for engine, metadata in self._ENGINE_METADATA.items():
            fp16_gb = float(metadata["fp16_gb"])
            total_bits = fp16_gb * (1024**3) * 8
            seconds = total_bits / (bandwidth_mbps * 1_000_000)
            total_seconds += seconds
            estimates[engine] = {
                "fp16_gb": fp16_gb,
                "estimated_minutes": round(seconds / 60.0, 2),
                "estimated_hours": round(seconds / 3600.0, 2),
            }

        estimates["totals"] = {
            "estimated_minutes": round(total_seconds / 60.0, 2),
            "estimated_hours": round(total_seconds / 3600.0, 2),
        }
        return estimates


WeightSyncManager = SyncManager
