"""Adapter for the VINS-Fusion multi-sensor state-estimation stack.

Military/tactical context:
This wrapper provides secure, offline-friendly checks for visual-inertial and
GPS-fusion navigation pipelines used in contested mission environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class VinsFusionAdapter(IntegrationAdapter):
    """Expose VINS-Fusion capabilities for tactical navigation workflows."""

    integration_id = "vins-fusion"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("vins_estimator", "vins_node", "ros2", "rospack")
    _ROS_PACKAGES = ("vins", "vins_estimator", "vins_fusion")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.navigation.vins-fusion")
        self._manifest_cache: IntegrationManifest | None = None

    @property
    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        if not self._manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", self._manifest_path)
            return {}
        try:
            raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", self._manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest is not a mapping: %s", self._manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for mission-estimator wrapper discovery."""
        if self._manifest_cache is not None:
            return self._manifest_cache

        raw = self._load_manifest_dict()
        self._manifest_cache = IntegrationManifest(
            name=str(raw.get("name", "VINS-Fusion")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(
                raw.get("source_url", "https://github.com/HKUST-Aerial-Robotics/VINS-Fusion")
            ),
            license=str(raw.get("license", "(BSD-style)")),
            description=str(
                raw.get(
                    "description",
                    "Optimization-based multi-sensor state estimator for aerial and ground platforms.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=[
                str(item)
                for item in raw.get(
                    "capabilities",
                    ["visual_inertial_odometry", "stereo_fusion", "gps_fusion"],
                )
            ],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", ["ros"])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )
        return self._manifest_cache

    def _probe_ros_packages(self) -> bool:
        for package in self._ROS_PACKAGES:
            ros2_bin = shutil.which("ros2")
            if ros2_bin:
                try:
                    probe = subprocess.run(
                        [ros2_bin, "pkg", "prefix", package],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=8,
                    )
                except (subprocess.SubprocessError, OSError):
                    probe = None
                if probe and probe.returncode == 0:
                    return True

            rospack_bin = shutil.which("rospack")
            if rospack_bin:
                try:
                    probe = subprocess.run(
                        [rospack_bin, "find", package],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=8,
                    )
                except (subprocess.SubprocessError, OSError):
                    probe = None
                if probe and probe.returncode == 0:
                    return True
        return False

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure tactical execution.")

        safe_params: dict[str, Any] = {}
        for key, value in params.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_params[key] = value
            elif isinstance(value, list):
                safe_params[key] = [item for item in value if isinstance(item, (str, int, float, bool))]
        return safe_params

    def validate_availability(self) -> bool:
        """Check local VINS-Fusion binaries/packages for navigation readiness."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        if any(shutil.which(command) for command in self._COMMAND_CANDIDATES):
            return True

        return self._probe_ros_packages()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute adapter workflow with deterministic airgapped fixture mode."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation", "fuse_visual_inertial_state"))

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": self.validate_availability(),
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "VINS-Fusion runtime is not installed or configured on this node.",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "request": request,
            "note": "VINS-Fusion local checks passed; live execution is mission-policy controlled.",
        }
