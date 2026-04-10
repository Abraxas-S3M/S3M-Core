"""Adapter for crazyswarm (extensions) swarm operations.

Military/tactical context:
This wrapper hardens swarm integration checks so mission operators can rehearse
coordinated multi-agent maneuvers on sovereign, airgapped edge infrastructure.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CrazyswarmextensionsAdapter(IntegrationAdapter):
    """S3M swarm adapter for crazyswarm (extensions)."""

    integration_id = "crazyswarm-extensions"
    domain = "swarm"
    _COMMAND_CANDIDATES = ('ros2', 'colcon', 'python3', 'cfclient')
    _DEFAULT_OPERATION = "synchronize_drone_swarm"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.swarm.crazyswarm-extensions")

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

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted mission parameters before tactical execution."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", self._DEFAULT_OPERATION)
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        return dict(request)

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for S3M swarm capability discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "crazyswarm (extensions)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/USC-ACTLab/crazyswarm"),
            license=str(raw.get("license") or "MIT"),
            description=str(raw.get("description") or "Control framework for Crazyflie drone swarms with ROS2-compatible extension wrappers."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or [
                    "swarm_state_estimation",
                    "multi_agent_coordination",
                    "ros2_tactical_rehearsal",
                ]
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["ros2", "colcon"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability without any external API calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper workflow with deterministic airgapped fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation", self._DEFAULT_OPERATION))

        if self.is_airgapped:
            # Tactical operators depend on deterministic replay data during disconnected rehearsals.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
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
                "error": "Local swarm runtime is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "Crazyswarm extensions are ready for synchronized drone swarm command rehearsals.",
        }
