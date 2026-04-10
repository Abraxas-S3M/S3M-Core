"""Adapter for multi-agent active SLAM reinforcement-learning workflows.

Military/tactical context:
This wrapper supports decentralized exploration and map-fusion readiness checks
for multi-vehicle scouting teams operating in contested, disconnected terrain.
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


class MultiAgentReinforcementLearningAdapter(IntegrationAdapter):
    """S3M wrapper for active-SLAM multi-agent reinforcement-learning pipelines."""

    integration_id = "multi-agent-reinforcement-learning-activ"
    domain = "swarm"
    _DEFAULT_OPERATION = "run_active_slam_episode"
    _COMMAND_CANDIDATES = ("ros2", "colcon", "gazebo")
    _MODULE_CANDIDATES = ("rclpy", "nav2_msgs")
    _ENV_PATH_KEYS = (
        "MULTI_AGENT_REINFORCEMENT_LEARNING_ACTIVE_SLAM_PATH",
        "MULTI_AGENT_REINFORCEMENT_LEARNING_ACTIVE_SLAM_ROOT",
    )

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.swarm.multi-agent-reinforcement-learning-activ"
        )

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
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate decentralized SLAM task requests before execution."""
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
        """Load adapter metadata for sovereign swarm mission orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "multi-agent-reinforcement-learning-active-slam"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/i1Cps/multi-agent-reinforcement-learning-active-slam"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "ROS2 packages for decentralized multi-agent active SLAM and DRL."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["decentralized_exploration", "active_slam", "map_fusion"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local ROS2/SLAM runtime readiness without external network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        if any(importlib.util.find_spec(module) for module in self._MODULE_CANDIDATES):
            return True

        for env_key in self._ENV_PATH_KEYS:
            configured = self._env(env_key)
            if configured and Path(configured).expanduser().exists():
                return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute active-SLAM wrapper behavior with deterministic fixture fallback."""
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
            self.logger.info(
                "Airgapped mode active; returning multi-agent active-SLAM fixture payload."
            )
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
                "message": "multi-agent active-SLAM runtime is not installed or configured locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "active-SLAM dependencies validated for local multi-agent exploration pipeline.",
        }
