"""Adapter for ros-sensor-fusion-tutorial EKF/UKF workflows.

Military/tactical context:
This wrapper supports mission-state estimation drills by validating local EKF/UKF
toolchain readiness and replaying deterministic fused-track outputs when the node
operates in airgapped sovereign environments.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RosSensorFusionTutorialAdapter(IntegrationAdapter):
    """S3M adapter for ROS sensor fusion tutorial pipelines."""

    integration_id = "ros-sensor-fusion-tutorial"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ("ros2", "robot_localization", "python3")
    _PYTHON_MODULE_CANDIDATES = ("rclpy", "numpy")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical replay analytics expect this stable logger namespace.
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.ros-sensor-fusion-tutorial")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw_manifest, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for tactical EKF/UKF training orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "ros-sensor-fusion-tutorial"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Tutorial and examples for ROS robot_localization EKF/UKF sensor fusion."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["ekf-state-estimation", "ukf-state-estimation", "multi-sensor-fusion-training"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Verify local ROS fusion tooling is available in sovereign deployments."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        modules_ready = any(importlib.util.find_spec(name) for name in self._PYTHON_MODULE_CANDIDATES)
        commands_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return modules_ready or commands_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute sensor-fusion tutorial wrapper with fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        operation = request.get("operation", "fuse_tracks")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "operation must be a non-empty string with at most 64 characters",
            }

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "error": "required local tooling is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local ROS fusion toolchain detected; execution remains mission-policy controlled.",
        }
