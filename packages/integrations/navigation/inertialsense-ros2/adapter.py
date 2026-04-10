"""Adapter for inertialsense_ros2 RTK-GPS-INS integration.

Military/tactical context:
This wrapper validates denied-environment inertial fusion readiness so convoy
and unmanned systems can sustain navigation when GNSS is degraded or denied.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class InertialsenseRos2Adapter(IntegrationAdapter):
    """S3M adapter for inertialsense-ros2 localization and fusion workflows."""

    integration_id = "inertialsense-ros2"
    domain = "navigation"

    _COMMAND_CANDIDATES = ("ros2", "python3")
    _PYTHON_MODULE_CANDIDATES = ("rclpy",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
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
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical navigation orchestrators."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "inertialsense_ros2")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "ROS2 wrapper for InertialSense RTK-GPS-INS with denied-environment fusion support.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["imu-gnss-fusion", "ros2-telemetry", "denied-navigation-readiness"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local ROS2 runtime readiness for inertial fusion pipelines."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        modules_ready = any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES)
        commands_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return modules_ready and commands_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute denied-fusion readiness checks with fixture fallback."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request = params or {}
        operation = str(request.get("operation", "imu_gnss_fusion_status"))

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving fixture data for %s.", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "ROS2 runtime is unavailable for inertialsense integration",
                "operation": operation,
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local ROS2 checks passed; live sensor stream execution remains mission-policy gated.",
        }
