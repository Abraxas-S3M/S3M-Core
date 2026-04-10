"""Adapter for fuse nonlinear multi-sensor estimation workflows.

Military/tactical context:
This wrapper supports resilient state-estimation readiness checks used by
autonomous platforms operating in GNSS-denied and contested environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class FuseAdapter(IntegrationAdapter):
    """S3M adapter for locusrobotics/fuse sensor-fusion workflows."""

    integration_id = "fuse"
    domain = "sensor_fusion"
    _DEFAULT_OPERATION = "estimate_platform_state"
    _COMMAND_CANDIDATES = ("ros2", "colcon", "fuse_core")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.fuse")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}

        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}

        if not isinstance(loaded, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical estimator orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "fuse")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/locusrobotics/fuse")),
            license=str(raw.get("license", "BSD")),
            description=str(
                raw.get(
                    "description",
                    "ROS framework for nonlinear least-squares fusion of GNSS, IMU, and odometry.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["nonlinear_state_estimation", "multi_sensor_fusion", "ros_graph_integration"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime readiness without any network dependency."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute deterministic wrapper behavior with airgapped fixture mode."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure tactical sensor fusion.")
        request = params or {}
        operation = str(request.get("operation", self._DEFAULT_OPERATION))

        if self.is_airgapped:
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "operation": operation,
                "available": False,
                "error": "fuse runtime dependencies are not installed or configured.",
                "request": request,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "operation": operation,
            "available": True,
            "request": request,
            "note": "fuse readiness checks passed for tactical multi-sensor state estimation.",
        }
