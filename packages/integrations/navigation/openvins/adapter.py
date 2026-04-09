"""Adapter for the OpenVINS visual-inertial navigation platform.

Military/tactical context:
This wrapper standardizes OpenVINS availability checks and offline execution
simulation so tactical navigation services can be rehearsed in sovereign nodes.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenvinsAdapter(IntegrationAdapter):
    """Expose OpenVINS capabilities for mission-state estimation workflows."""

    integration_id = "openvins"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("ov_msckf", "ov_eval")
    _ROS_PACKAGES = ("ov_core", "ov_msckf", "open_vins")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.navigation.openvins")
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
        """Return metadata for OpenVINS navigation wrapper registration."""
        if self._manifest_cache is not None:
            return self._manifest_cache

        raw = self._load_manifest_dict()
        self._manifest_cache = IntegrationManifest(
            name=str(raw.get("name", "OpenVINS")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/rpng/open_vins")),
            license=str(raw.get("license", "(BSD-style)")),
            description=str(
                raw.get(
                    "description",
                    "Filter-based visual-inertial navigation platform with ROS2 support.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=[
                str(item)
                for item in raw.get(
                    "capabilities",
                    ["visual_inertial_tracking", "filter_based_estimation", "ros2_support"],
                )
            ],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", ["ros2"])],
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
        """Check local OpenVINS availability without external network dependencies."""
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
        """Execute OpenVINS wrapper behavior with fixture fallback in airgap."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation", "track_visual_inertial_state"))

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
                "error": "OpenVINS runtime is not installed or configured on this node.",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "request": request,
            "note": "OpenVINS local checks passed; mission execution remains under tactical policy control.",
        }
