"""Adapter for Military_Drones (VorteX) swarm surveillance simulation.

Military/tactical context:
This wrapper supports sovereign multi-drone surveillance rehearsal by checking
ROS2/Gazebo Harmonic availability and providing deterministic fixture replay
for mission planning in disconnected command environments.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryDronesvortexAdapter(IntegrationAdapter):
    """S3M simulation adapter for Military_Drones (VorteX)."""

    integration_id = "military-drones-vortex"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("ros2", "gz", "gazebo", "colcon")
    _ENV_PATH_KEYS = ("MILITARY_DRONES_VORTEX_PATH", "VORTEX_PATH")
    _ENV_BIN_KEY = "MILITARY_DRONES_VORTEX_BIN"
    _MODULE_CANDIDATES = ("rclpy", "launch")
    _DEFAULT_OPERATION = "coordinate_multi_drone_surveillance"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.military-drones-vortex")

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
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate surveillance mission parameters before tactical execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata loaded from this package manifest."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Military_Drones (VorteX)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/Manohara-Ai/VorteX"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "ROS2 Humble and Gazebo Harmonic multi-drone surveillance simulation."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["multi_drone_surveillance", "formation_control", "ros2_gazebo_harmonic_rehearsal"],
                )
            ),
            system_dependencies=list(raw.get("system_dependencies", ["ros2", "gz"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local VorteX dependencies without external service calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_paths = [self._env(key) for key in self._ENV_PATH_KEYS]
        if any(path and Path(path).expanduser().exists() for path in configured_paths):
            return True

        configured_bin = self._env(self._ENV_BIN_KEY).strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        if any(shutil.which(command) for command in self._COMMAND_CANDIDATES):
            return True

        return any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper behavior with deterministic airgapped fixture replay."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)
        if self.is_airgapped:
            self.logger.info("Airgapped mode enabled; returning VorteX fixture output.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "Military_Drones VorteX runtime is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "VorteX dependencies validated for sovereign multi-drone surveillance rehearsal.",
        }
