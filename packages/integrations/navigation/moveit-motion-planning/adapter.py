"""Adapter for MoveIt motion planning workflows.

Military/tactical context:
This wrapper validates local motion-planning stack readiness for autonomous
platform maneuver planning in contested environments with strict safety bounds.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MoveitmotionPlanningAdapter(IntegrationAdapter):
    """S3M adapter for moveit-motion-planning mission maneuver workflows."""

    integration_id = "moveit-motion-planning"
    domain = "navigation"

    _COMMAND_CANDIDATES = ("move_group", "ros2", "python3")
    _PYTHON_MODULE_CANDIDATES = ("moveit_commander", "ompl")

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

    def get_manifest(self) -> IntegrationManifest:
        """Return MoveIt metadata for tactical motion orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "MoveIt (motion planning)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Robot motion planning framework with OMPL integration and planning-scene controls.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["motion-planning", "collision-checking", "trajectory-execution-readiness"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local MoveIt stack for offline mission-planning readiness."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        modules_ready = any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES)
        commands_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return modules_ready or commands_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute motion-planning readiness workflow with fixture fallback."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request = params or {}
        operation = str(request.get("operation", "plan_path"))

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving fixture data for %s.", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "MoveIt runtime is unavailable on this node",
                "operation": operation,
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local MoveIt checks passed; live planning/execution remains mission-policy controlled.",
        }
