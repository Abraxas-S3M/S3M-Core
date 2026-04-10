"""Adapter for lidar_radar_fusion_ekf_ukf tactical tracking workflows.

Military/tactical context:
This wrapper helps validate fused LiDAR/radar state-estimation readiness for
tracking high-velocity contacts in degraded visibility and EW-contested sectors.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class LidarRadarFusionEkfAdapter(IntegrationAdapter):
    """S3M adapter for lidar-radar-fusion-ekf-ukf state-estimation workflows."""

    integration_id = "lidar-radar-fusion-ekf-ukf"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ("lidar_radar_fusion", "cmake", "g++")
    _SOURCE_DIR_HINTS = ("src", "include")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical telemetry observability depends on this deterministic logger key.
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.lidar-radar-fusion-ekf-ukf")

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
        """Load metadata for LiDAR/radar tactical fusion orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "lidar_radar_fusion_ekf_ukf"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/cggos/lidar_radar_fusion_ekf_ukf"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "C++ EKF/UKF fusion implementation for LiDAR and radar target tracking."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["lidar-radar-fusion", "ekf-tracking", "ukf-tracking", "trajectory-estimation"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Verify local fusion toolchain availability without external network usage."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_bin = self._env(f"{env_prefix}_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path:
            repo_path = Path(configured_path).expanduser()
            if repo_path.exists() and any((repo_path / hint).exists() for hint in self._SOURCE_DIR_HINTS):
                return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute fusion workflow wrapper with offline fixture replay."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", "track_target")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

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
            "note": "Local LiDAR/radar fusion toolchain detected; mission-policy gates remain in force.",
        }
