"""TacticalMesh adapter for resilient coalition networking simulation.

Military/tactical context:
This wrapper normalizes TacticalMesh interactions so command nodes can evaluate
resilient decentralized C2 message routing in contested and disconnected
environments.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class TacticalmeshAdapter(IntegrationAdapter):
    """Adapter for decentralized TacticalMesh interoperability workflows."""

    integration_id = "tacticalmesh"
    domain = "interop"
    _SUPPORTED_OPERATIONS = {"mesh_topology_snapshot", "route_health_check", "link_resilience_report"}
    _TOOL_MODULES = ("tacticalmesh",)
    _TOOL_COMMANDS = ("tacticalmesh", "meshd", "meshctl")

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
            name=str(raw.get("name") or "TacticalMesh"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/TamTunnel/TacticalMesh"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Decentralized mesh networking wrapper for resilient coalition C2 operations."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["mesh_topology_management", "link_resilience_monitoring", "c2_message_routing"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local dependencies needed for TacticalMesh workflows."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("TACTICALMESH_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        module_available = any(importlib.util.find_spec(name) is not None for name in self._TOOL_MODULES)
        command_available = any(shutil.which(command) is not None for command in self._TOOL_COMMANDS)
        mirror_available = Path("/opt/s3m/interop/tacticalmesh").exists()
        return module_available or command_available or mirror_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper workflow or return deterministic airgapped fixture."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "mesh_topology_snapshot").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture mesh-state data for disconnected C2 networking rehearsal.")
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
                "message": "TacticalMesh dependencies are not available on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "accepted",
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Runtime handoff prepared for local TacticalMesh execution.",
        }
