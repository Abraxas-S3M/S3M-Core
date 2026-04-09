"""Adapter for the mav_multiagent_ws multi-UAV coordination workspace.

Military/tactical context:
This wrapper supports sovereign rehearsal of multi-UAV task allocation and
deconfliction workflows so distributed aerial teams can be coordinated in
airgapped command infrastructure.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MavMultiagentWsAdapter(IntegrationAdapter):
    """S3M integration adapter for mav_multiagent_ws coordination workflows."""

    integration_id = "mav-multiagent-ws"
    domain = "military"
    _COMMAND_CANDIDATES = ("roslaunch", "catkin_make", "roscore", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.mav-multiagent-ws")

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

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted multi-agent tasking payloads before processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        payload = json.loads(json.dumps(params))
        if len(json.dumps(payload)) > 20000:
            raise ValueError("params payload is too large")
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata for orchestrator capability discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "mav_multiagent_ws")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/ethz-asl/mav_multiagent_ws")),
            license=str(raw.get("license", "(BSD-style)")),
            description=str(
                raw.get(
                    "description",
                    "ROS workspace for multi-UAV swarm coordination.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["multi-uav-coordination", "swarm-task-allocation", "airspace-deconfliction"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local mav_multiagent_ws prerequisites without network calls."""
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
        """Run multi-agent workspace wrapper logic with fixture fallback."""
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

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning multi-agent fixture for swarm rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": request_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "mav_multiagent_ws stack is not installed or configured",
                "request": request_params,
            }

        operation = str(request_params.get("operation", "coordinate_multi_uav"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local multi-agent checks passed; live coordination is delegated to mission autonomy orchestration.",
        }
