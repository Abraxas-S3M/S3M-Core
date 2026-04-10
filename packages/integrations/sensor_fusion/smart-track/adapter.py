"""Adapter for Smart Track multi-sensor tracking workflows.

Military/tactical context:
This wrapper validates RGB-Depth-LiDAR fusion readiness so field operators can
rehearse resilient tracking behavior in degraded and GPS-contested theaters.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SmartTrackAdapter(IntegrationAdapter):
    """S3M integration adapter for the smart_track repository."""

    integration_id = "smart-track"
    domain = "sensor_fusion"

    _DEFAULT_OPERATION = "multi_sensor_tracking"
    _COMMAND_CANDIDATES = ("ros2", "colcon", "python3")
    _SUPPORTED_OPERATIONS = {
        "multi_sensor_tracking",
        "rgb_depth_lidar_fusion",
        "track_state_estimation",
    }

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate request payloads for secure tactical fusion execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for tactical sensor-fusion execution.")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings.")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable.") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large.")
        return normalized

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

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for S3M orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "smart_track")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/mzahana/smart_track")),
            license=str(raw.get("license", "MIT")),
            description=str(
                raw.get(
                    "description",
                    "Kalman Filter-Guided Sensor Fusion for robust object tracking using RGB-Depth-LiDAR in ROS2.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    ["rgb_depth_lidar_fusion", "kalman_filter_tracking", "ros2_object_tracking"],
                )
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies", ["ros2", "python3", "colcon"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local availability without external API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper with deterministic fixture replay in airgapped mode."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation", self._DEFAULT_OPERATION)).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            # Tactical command posts need deterministic replay when isolated.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "data": self._read_fixture("sample_response.json"),
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
                "error": "smart_track runtime dependencies are not installed or configured on this node.",
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
            "note": "smart_track adapter is validated for local multi-modal tracking readiness checks.",
        }
