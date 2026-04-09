"""Adapter for West Point multirotor ROS launch workflows.

Military/tactical context:
This wrapper standardizes UAV launch-plan staging for multirotor assets used in
contested environments, enabling deterministic mission rehearsal when the node
is disconnected from external services.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MultirotorLaunchwestPointAdapter(IntegrationAdapter):
    """S3M integration adapter for West Point multirotor launch files."""

    integration_id = "multirotor-launch-west-point"
    domain = "military"
    _COMMAND_CANDIDATES = ("roslaunch", "ros2", "roscore")
    _SUPPORTED_OPERATIONS = {"launch_uav_mission", "status_check", "validate_launch_plan"}

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
        """Return adapter metadata used by tactical orchestration controls."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "multirotor_launch (West Point)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "ROS launch wrappers for multirotor UAV control integrated with GLAWS mission workflows.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["uav-launch-orchestration", "mission-profile-validation", "airgapped-rehearsal"],
                )
            ),
            system_dependencies=list(raw.get("system_dependencies", ["roslaunch"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local ROS launch tooling without any remote network dependency."""
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

    def _sanitize_package_name(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("package_name must be a string")
        package_name = value.strip()
        if not package_name:
            raise ValueError("package_name cannot be empty")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", package_name):
            raise ValueError("package_name contains invalid characters")
        return package_name

    def _sanitize_launch_file(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("launch_file must be a string")
        launch_file = value.strip()
        if not launch_file:
            raise ValueError("launch_file cannot be empty")
        launch_path = Path(launch_file)
        if launch_path.is_absolute() or ".." in launch_path.parts:
            raise ValueError("launch_file must be a relative path without traversal")
        return launch_file

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute launch wrapper behavior with deterministic offline fixture replay."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "launch_uav_mission")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        package_name = self._sanitize_package_name(request.get("package_name", "glaws_multirotor"))
        launch_file = self._sanitize_launch_file(request.get("launch_file", "multirotor_mission.launch"))

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning UAV launch fixture for mission rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": {
                    "package_name": package_name,
                    "launch_file": launch_file,
                    "params": request.get("params", {}),
                },
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "ROS launch tooling is not installed or configured",
                "operation": operation,
                "request": {
                    "package_name": package_name,
                    "launch_file": launch_file,
                    "params": request.get("params", {}),
                },
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "runtime",
            "operation": operation,
            "command": f"roslaunch {package_name} {launch_file}",
            "request": {
                "package_name": package_name,
                "launch_file": launch_file,
                "params": request.get("params", {}),
            },
            "note": "Local launch stack is reachable; live mission execution remains controlled by authorized flight nodes.",
        }
