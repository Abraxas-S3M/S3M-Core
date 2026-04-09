"""Adapter for nmpc_px4_ros2 navigation integration.

Military/tactical context:
This wrapper standardizes deterministic navigation-control outputs so mission
operators can validate planning and control readiness while disconnected from
external networks and contested communications environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class NmpcPx4Ros2Adapter(IntegrationAdapter):
    """S3M adapter for nmpc-px4-ros2."""

    integration_id = "nmpc-px4-ros2"
    domain = "navigation"
    _SUPPORTED_OPERATIONS = {
        "uav_tracking",
        "health_probe",
        "mission_rehearsal",
    }
    _MODULE_CANDIDATES = ('px4_msgs', 'rclpy')
    _COMMAND_CANDIDATES = ('ros2', 'px4', 'colcon')

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(data, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}

        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for tactical orchestrator discovery."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name", "nmpc_px4_ros2")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(raw.get("description", "")),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", [])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime readiness for contested, disconnected operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        module_ready = any(importlib.util.find_spec(module_name) is not None for module_name in self._MODULE_CANDIDATES)
        command_ready = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_ready or command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run integration handoff with deterministic fixture fallback."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request = params or {}
        operation = str(request.get("operation", "uav_tracking")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": f"unsupported operation: {operation}",
                "supported_operations": sorted(self._SUPPORTED_OPERATIONS),
                "request": request,
            }

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving navigation fixture for %s.", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": request,
                "message": "nmpc_px4_ros2 runtime dependencies are unavailable.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "PX4 NMPC adapter validated locally; command execution is delegated to mission flight stack.",
        }
