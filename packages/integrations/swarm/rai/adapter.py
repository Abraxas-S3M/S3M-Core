"""Adapter for the RAI ROS2 physical-AI framework.

Military/tactical context:
This wrapper enables sovereign validation of vendor-agnostic agentic robotics
pipelines for multi-domain swarm operations on controlled defense networks.
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


class RaiAdapter(IntegrationAdapter):
    """S3M adapter for RAI physical-AI robotics workflows."""

    integration_id = "rai"
    domain = "swarm"
    _DEFAULT_OPERATION = "agentic_pipeline_readiness"
    _COMMAND_CANDIDATES = ("rai", "ros2")
    _ENV_PATH_KEYS = ("RAI_PATH", "RAI_ROOT")
    _MODULE_CANDIDATES = ("rclpy",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.rai")

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
        """Validate untrusted payloads before tactical robotics wrapper execution."""
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
        """Load integration metadata for tactical robotics discovery workflows."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "rai"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/RobotecAI/rai"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Vendor-agnostic agentic framework for Physical AI robotics using ROS2."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["agentic_robotics", "ros2_integration", "vendor_agnostic_orchestration"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local RAI runtime dependencies without external API requests."""
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
        """Execute wrapper behavior with deterministic airgapped fixture replay."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical policy: disconnected command nodes use local fixture replay only.
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
                "error": "RAI runtime is not installed or configured on this node.",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "message": "RAI dependencies validated for sovereign local physical-AI orchestration.",
        }
