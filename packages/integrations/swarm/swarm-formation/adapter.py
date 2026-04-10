"""Adapter for the Swarm-Formation distributed trajectory-optimization project.

Military/tactical context:
This wrapper supports sovereign validation of dense-environment formation flight
plans for multi-UAV patrol and strike-support operations.
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


class SwarmFormationAdapter(IntegrationAdapter):
    """S3M adapter for Swarm-Formation distributed swarm trajectory workflows."""

    integration_id = "swarm-formation"
    domain = "swarm"
    _DEFAULT_OPERATION = "distributed_formation_optimization"
    _COMMAND_CANDIDATES = ("swarm_formation", "ros2", "colcon")
    _ENV_PATH_KEYS = ("SWARM_FORMATION_PATH", "SWARM_FORMATION_ROOT")
    _MODULE_CANDIDATES = ("rclpy",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.swarm-formation")

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
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
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
        """Validate untrusted task payloads before tactical trajectory execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        normalized = json.loads(json.dumps(params))
        if len(json.dumps(normalized)) > 25_000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for tactical formation-planning discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Swarm-Formation"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/ZJU-FAST-Lab/Swarm-Formation"),
            license=str(raw.get("license") or "GPLv3"),
            description=str(
                raw.get("description")
                or "Distributed swarm trajectory optimization for dense-environment formation flight."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["formation_optimization", "distributed_planning", "dense_environment_navigation"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability with no external API dependencies."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if any(
            self._env(key) and Path(self._env(key)).expanduser().exists()  # noqa: PTH110
            for key in self._ENV_PATH_KEYS
        ):
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper behavior with deterministic fixture fallback offline."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical policy: use deterministic fixture replay in disconnected theaters.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "request": request,
                "error": "Swarm-Formation runtime is not installed or configured on this node.",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "message": "Swarm-Formation dependencies validated for local distributed trajectory planning.",
        }
