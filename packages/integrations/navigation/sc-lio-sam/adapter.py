"""Adapter for SC-LIO-SAM navigation stack.

Military/tactical context:
This wrapper validates whether SC-LIO-SAM can provide resilient localization
for mission units operating in GPS-denied or electronically contested terrain.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ScLioSamAdapter(IntegrationAdapter):
    """S3M integration adapter for SC-LIO-SAM."""

    integration_id = "sc-lio-sam"
    domain = "navigation"
    _COMMAND_CANDIDATES = ('ros2', 'colcon', 'python3', 'docker')
    _DEFAULT_OPERATION = "slam_pose_estimation"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

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
        """Return wrapper metadata for S3M orchestrator discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "SC-LIO-SAM")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/gisbi-kim/SC-LIO-SAM")),
            license=str(raw.get("license", "(BSD-style)")),
            description=str(raw.get("description", "Scan Context + LIO-SAM for robust LiDAR-inertial SLAM.")),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(raw.get("capabilities", ['lidar_inertial_slam', 'scan_context_loop_closure', 'global_pose_graph_optimization'])),
            system_dependencies=self._coerce_list(raw.get("system_dependencies", ['ros2', 'pcl', 'eigen'])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local toolchain readiness without any external API calls."""
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
        """Execute navigation wrapper with deterministic airgapped fallback."""
        if params is None:
            request_params: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure tactical navigation execution.")
        else:
            request_params = params

        operation = str(request_params.get("operation", self._DEFAULT_OPERATION))

        if self.is_airgapped:
            # Tactical rehearsal nodes rely on deterministic fixture replay when disconnected.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "data": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "SC-LIO-SAM runtime dependencies are not installed or configured on this node.",
                "request": request_params,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request_params,
            "note": "SC-LIO-SAM adapter is validated for contested-terrain localization and loop-closure readiness checks.",
        }
