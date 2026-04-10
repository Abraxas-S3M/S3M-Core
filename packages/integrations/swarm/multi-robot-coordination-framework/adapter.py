"""Adapter for Multi-Robot-Coordination-Framework distributed RL workflows.

Military/tactical context:
This wrapper standardizes distributed task-allocation rehearsals for robotic
teams conducting fault-tolerant patrol, resupply, and area-control operations
when links are contested and node failures must be absorbed.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MultiRobotCoordinationFrameworkAdapter(IntegrationAdapter):
    """S3M adapter for Multi-Robot-Coordination-Framework integration workflows."""

    integration_id = "multi-robot-coordination-framework"
    domain = "swarm"
    _COMMAND_CANDIDATES = ("ros2", "python3")
    _MODULE_CANDIDATES = ("rclpy", "torch", "numpy")
    _DEFAULT_OPERATION = "distributed_task_allocation"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.multi-robot-coordination-framework")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted distributed-tasking payloads before planning."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            payload = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(payload)) > 25000:
            raise ValueError("params payload is too large")
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for distributed multi-robot capability discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Multi-Robot-Coordination-Framework"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/JayDS22/Multi-Robot-Coordination-Framework"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Distributed RL framework for multi-robot task allocation with fault-tolerant ROS2 architecture."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    [
                        "distributed_task_allocation",
                        "fault_tolerant_coordination",
                        "multi_robot_rl",
                    ],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local framework prerequisites without external APIs."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute coordination wrapper behavior with deterministic offline fallback."""
        try:
            request_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(request_params.get("operation") or self._DEFAULT_OPERATION)
        if self.is_airgapped:
            self.logger.info(
                "Airgapped mode active; returning Multi-Robot-Coordination-Framework fixture payload."
            )
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "request": request_params,
                "message": "Multi-Robot-Coordination-Framework runtime is not installed or configured locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "message": "Framework dependencies validated; orchestrator may run distributed swarm coordination flow.",
        }

