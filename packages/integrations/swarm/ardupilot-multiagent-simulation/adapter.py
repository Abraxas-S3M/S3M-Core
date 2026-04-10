"""Adapter for Ardupilot_Multiagent_Simulation swarm rehearsal workflows.

Military/tactical context:
This wrapper standardizes multi-agent simulation readiness for mission planning,
formation validation, and command rehearsal before live autonomous deployment.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ArdupilotMultiagentSimulationAdapter(IntegrationAdapter):
    """S3M wrapper for Ardupilot_Multiagent_Simulation integration."""

    integration_id = "ardupilot-multiagent-simulation"
    domain = "swarm"
    _COMMAND_CANDIDATES = ("python3", "ros2", "gz", "gazebo", "arducopter")
    _MODULE_CANDIDATES = ("rclpy", "numpy")
    _DEFAULT_OPERATION = "launch_multiagent_rehearsal"

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
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate simulation requests before execution in tactical rehearsal."""
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
        """Return metadata for ArduPilot multi-agent simulation discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Ardupilot_Multiagent_Simulation"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/aau-cns/Ardupilot_Multiagent_Simulation"
            ),
            license=str(raw.get("license") or "GPL-3.0"),
            description=str(
                raw.get("description")
                or "Simulation environment for ArduPilot multi-agent drone systems."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    [
                        "multiagent_simulation",
                        "ardupilot_ros2_gazebo_integration",
                        "pre_mission_rehearsal_validation",
                    ],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local simulation toolchain without external services."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        if any(importlib.util.find_spec(name) is not None for name in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute simulation wrapper behavior with airgapped fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning ArduPilot simulation fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "ArduPilot multi-agent simulation dependencies are unavailable locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local simulation readiness checks passed; orchestrator may run rehearsal.",
        }
