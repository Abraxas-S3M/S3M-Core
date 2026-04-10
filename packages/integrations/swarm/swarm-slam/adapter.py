"""Adapter for Swarm-SLAM decentralized collaborative mapping workflows.

Military/tactical context:
This wrapper validates decentralized SLAM readiness for multi-robot teams that
must maintain a shared battlespace map in GPS-denied or communications-limited
missions while running fully offline on sovereign infrastructure.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SwarmSlamAdapter(IntegrationAdapter):
    """S3M integration adapter for the Swarm-SLAM repository."""

    integration_id = "swarm-slam"
    domain = "swarm"
    _COMMAND_CANDIDATES = ("swarm-slam", "swarm_slam", "run_swarm_slam")
    _MODULE_CANDIDATES = ("swarm_slam",)
    _DEFAULT_OPERATION = "collaborative_sparse_mapping"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(f"s3m.integrations.swarm.{self.integration_id}")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Failed to parse manifest YAML: %s", manifest_path)
            return {}

        if not isinstance(raw, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission parameters before tactical swarm mapping execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure swarm SLAM execution.")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings.")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable.") from exc

        if len(json.dumps(normalized)) > 50_000:
            raise ValueError("params payload is too large.")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return Swarm-SLAM metadata loaded from manifest.yaml."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Swarm-SLAM")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/MISTLab/Swarm-SLAM")),
            license=str(raw.get("license", "MIT")),
            description=str(
                raw.get("description")
                or "Sparse decentralized collaborative SLAM framework for multi-robot systems."
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    ["decentralized_slam", "collaborative_mapping", "pose_graph_fusion"],
                )
            ),
            system_dependencies=self._coerce_list(
                raw.get("system_dependencies", ["python3", "cmake"])
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check whether Swarm-SLAM is installed for local mission execution."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH") or self._env(f"{env_prefix}_ROOT")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute Swarm-SLAM wrapper behavior with deterministic offline fallback."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation", self._DEFAULT_OPERATION))
        if self.is_airgapped:
            # Tactical simulation nodes replay deterministic map-fusion fixtures offline.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": safe_params,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "Swarm-SLAM runtime dependencies are not installed or configured on this node.",
                "request": safe_params,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": safe_params,
            "note": "Swarm-SLAM adapter is ready for decentralized multi-robot mapping tasks.",
        }
