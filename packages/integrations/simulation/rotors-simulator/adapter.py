"""Adapter for rotors_simulator UAV simulation workflows.

Military/tactical context:
This wrapper supports rotorcraft mission rehearsal and autonomy validation with
deterministic fixture outputs for sovereign airgapped test ranges.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RotorsSimulatorAdapter(IntegrationAdapter):
    """S3M simulation adapter for rotors_simulator."""

    integration_id = "rotors-simulator"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("ros2", "roslaunch", "gazebo", "python3")
    _MODULE_CANDIDATES = ("rospy", "rclpy")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.rotors-simulator")

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
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    def get_manifest(self) -> IntegrationManifest:
        """Return rotors_simulator manifest metadata for simulation cataloging."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "rotors_simulator"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/ethz-asl/rotors_simulator"
            ),
            license=str(raw.get("license") or "(BSD-style)"),
            description=str(
                raw.get("description")
                or "Research-grade UAV simulator for ROS and autonomy testing."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["uav_dynamics_simulation", "ros_topic_replay", "controller_validation"]
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["ros2", "gazebo"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check if local ROS/rotors runtime components are available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        if any(shutil.which(command) for command in self._COMMAND_CANDIDATES):
            return True

        return any(importlib.util.find_spec(module_name) for module_name in self._MODULE_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute rotors_simulator operation with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("params must be a dictionary")

        operation = request.get("operation", "flight_dynamics_tick")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic UAV dynamics traces for repeatable evaluation.
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
                "error": "rotors_simulator is not installed or configured in this environment",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "rotors_simulator local runtime detected; external API calls remain disabled by policy.",
        }
