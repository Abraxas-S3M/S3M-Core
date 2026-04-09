"""coreDSUnreal sample adapter for DIS-enabled simulation interoperability.

Military/tactical context:
This wrapper standardizes sample DIS/Unreal interactions to support mission
simulation validation, including entity-state synchronization and deterministic
after-action playback in sovereign environments.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CoredsunrealsamplesAdapter(IntegrationAdapter):
    """Adapter for coreDSUnreal distributed simulation sample workflows."""

    integration_id = "coredsunreal-samples"
    domain = "interop"
    _SUPPORTED_OPERATIONS = {"dis_packet_bridge", "entity_state_sync", "exercise_playback"}
    _TOOL_MODULES = ("opendis",)
    _TOOL_COMMANDS = ("coreds", "disbridge", "unreal")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 64:
            raise ValueError("params contains too many top-level fields")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata from manifest.yaml for discovery."""
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or "coreDSUnreal (samples)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/distributedsimulationtools/coreDSUnreal_Sample_AutomaticMode"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "DIS integration sample adapter for Unreal Engine tactical simulation workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["dis_entity_sync", "simulation_playback", "protocol_interoperability"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local dependencies needed for DIS/Unreal simulation workflows."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("COREDSUNREAL_SAMPLES_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        module_available = any(importlib.util.find_spec(name) is not None for name in self._TOOL_MODULES)
        command_available = any(shutil.which(command) is not None for command in self._TOOL_COMMANDS)
        mirror_available = Path("/opt/s3m/interop/coredsunreal-samples").exists()
        return module_available or command_available or mirror_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper workflow or return deterministic airgapped fixture."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "entity_state_sync").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning coreDSUnreal fixture data for disconnected DIS simulation rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
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
                "source": "runtime",
                "operation": operation,
                "request": request,
                "message": "coreDSUnreal sample dependencies are not available on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "accepted",
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Runtime handoff prepared for local DIS/Unreal simulation execution.",
        }
