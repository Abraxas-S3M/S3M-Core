"""Adapter for drone_simulator cyber-physical UAV mission environments.

Military/tactical context:
This wrapper supports sovereign red/blue cyber-physical drone exercises by
validating ROS2/Gazebo simulation readiness and replaying deterministic
airgapped fixtures for defensive planning in disconnected theaters.
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


class DroneSimulatorcyberPhysicalAdapter(IntegrationAdapter):
    """S3M simulation adapter for the drone_simulator cyber-physical stack."""

    integration_id = "drone-simulator-cyber-physical"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("ros2", "gz", "gazebo", "colcon")
    _ENV_PATH_KEYS = ("DRONE_SIMULATOR_PATH", "DRONE_SIMULATOR_ROOT")
    _ENV_BIN_KEY = "DRONE_SIMULATOR_BIN"
    _MODULE_CANDIDATES = ("rclpy", "launch")
    _DEFAULT_OPERATION = "emulate_cyber_attack_scenario"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.drone-simulator-cyber-physical")

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
        """Validate cyber-range scenario parameters before mission simulation."""
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
            name=str(raw.get("name") or "drone_simulator (cyber-physical)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/patilunmesh/drone_simulator"
            ),
            license=str(raw.get("license") or "(Open)"),
            description=str(
                raw.get("description")
                or "ROS2-based UAV simulator for cyber-physical security attack/defense workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["cyber_attack_emulation", "uav_defense_drills", "ros2_gazebo_scenario_control"],
                )
            ),
            system_dependencies=list(raw.get("system_dependencies", ["ros2", "gz"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local simulator dependencies without any external API calls."""
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
            self.logger.info("Airgapped mode enabled; returning cyber-physical fixture output.")
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
                "message": "drone_simulator runtime is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "drone_simulator dependencies validated for tactical cyber-physical simulation.",
        }
