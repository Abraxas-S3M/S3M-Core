
"""Adapter for PX4_Swarm_Controller swarm operations.

Military/tactical context:
This wrapper supports sovereign multi-domain swarm mission rehearsal by
enforcing deterministic, airgapped-safe behavior for command workflows.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Px4SwarmControllerAdapter(IntegrationAdapter):
    """S3M swarm-domain adapter for PX4_Swarm_Controller."""

    integration_id = "px4-swarm-controller"
    domain = "swarm"
    _COMMAND_CANDIDATES = ('ros2', 'px4', 'gz', 'gazebo', 'colcon')
    _DEFAULT_OPERATION = "leader_follower_control_validation"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.px4-swarm-controller")

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
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate command payloads before tactical swarm orchestration."""
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
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata used by sovereign swarm orchestrators."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "PX4_Swarm_Controller"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/artastier/PX4_Swarm_Controller"),
            license=str(raw.get("license") or "MIT"),
            description=str(raw.get("description") or "ROS2 package for scalable multi-drone simulation and control in Gazebo using leader-follower patterns."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ['leader_follower_control', 'gazebo_swarm_simulation', 'px4_fleet_command_validation']),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ['ros2', 'px4', 'gz']),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime/toolchain availability without external network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper request with deterministic fallback for denied networks."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning PX4_Swarm_Controller fixture payload.")
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
                "message": "PX4_Swarm_Controller runtime dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local swarm readiness checks passed; live execution is orchestrator-governed.",
        }
