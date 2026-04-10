"""Adapter for Autonomous_UAVs_Swarm_Mission cooperative flight workflows.

Military/tactical context:
This wrapper standardizes swarm UAV coordination readiness checks for ISR,
area-denial observation, and mission continuity under attrition or comms loss.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AutonomousUavsSwarmMissionAdapter(IntegrationAdapter):
    """S3M wrapper for Autonomous_UAVs_Swarm_Mission integration."""

    integration_id = "autonomous-uavs-swarm-mission"
    domain = "swarm"
    _COMMAND_CANDIDATES = ("python3", "ros2")
    _MODULE_CANDIDATES = ("numpy", "networkx")
    _DEFAULT_OPERATION = "coordinate_uav_swarm_sortie"

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
        """Validate mission-request payloads prior to local swarm processing."""
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
        """Return metadata for cooperative UAV swarm mission integration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Autonomous_UAVs_Swarm_Mission"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/AlexJinlei/Autonomous_UAVs_Swarm_Mission"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Autonomous quadcopter swarm for cooperative multi-UAV missions."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    [
                        "cooperative_path_coordination",
                        "swarm_communication_resilience",
                        "failure_handling_retasking",
                    ],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local UAV swarm dependencies in sovereign offline mode."""
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
        """Execute UAV swarm adapter flow with airgapped fixture fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning UAV swarm fixture payload.")
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
                "message": "Autonomous_UAVs_Swarm_Mission dependencies are unavailable locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local UAV swarm readiness checks passed; mission execution can proceed.",
        }
