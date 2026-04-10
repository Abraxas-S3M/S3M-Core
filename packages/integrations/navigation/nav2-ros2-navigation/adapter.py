"""Adapter for nav2 (ROS2 Navigation).

Military/tactical context:
This wrapper checks local ROS2/nav2 readiness for autonomous ground and aerial
route execution in offline mission-control environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Nav2ros2NavigationAdapter(IntegrationAdapter):
    """S3M adapter for nav2 mission navigation workflows."""

    integration_id = "nav2-ros2-navigation"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("ros2", "nav2_bt_navigator", "nav2_controller")
    _DEFAULT_OPERATION = "plan_and_control_route"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.navigation.nav2-ros2-navigation")

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
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata for tactical route orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "nav2 (ROS2 Navigation)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/ros-planning/navigation2")),
            license=str(raw.get("license", "BSD")),
            description=str(
                raw.get(
                    "description",
                    "ROS2 navigation stack with planners, controllers, and behavior trees.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    ["global_planning", "local_control", "behavior_tree_navigation"],
                )
            ),
            system_dependencies=self._coerce_list(
                raw.get("system_dependencies", ["ros2", "nav2"])
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local nav2 runtime availability without external calls."""
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
        """Execute nav2 wrapper request with deterministic fixture fallback."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure tactical navigation execution.")
        else:
            request = params

        operation = str(request.get("operation", self._DEFAULT_OPERATION))
        if self.is_airgapped:
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "nav2 runtime is not installed or configured on this node.",
                "request": request,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "note": "nav2 checks passed for offline tactical route execution pipelines.",
        }
