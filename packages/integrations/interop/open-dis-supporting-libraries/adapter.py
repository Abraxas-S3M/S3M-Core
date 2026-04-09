"""Adapter for open-dis supporting libraries used in DIS interoperability.

Military/tactical context:
This wrapper gives simulation and C2 teams a deterministic interface for
coordinate conversion and PDU validation workflows during denied-network
operations on sovereign infrastructure.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenDisSupportingLibrariesAdapter(IntegrationAdapter):
    """Expose open-dis helper capabilities with airgapped fallback support."""

    integration_id = "open-dis-supporting-libraries"
    domain = "interop"

    _SUPPORTED_OPERATIONS = {"coordinate_convert", "pdu_validate", "pdu_summary"}
    _TOOL_MODULES = ("opendis", "open_dis", "dis7", "dis_utils")
    _TOOL_COMMANDS = ("open-dis", "dis-utils")
    _LOCAL_MIRROR_ENV = "OPEN_DIS_SUPPORTING_LIBRARIES_PATH"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission input before interoperability processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
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
        """Load adapter metadata used by sovereign orchestration."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "open-dis supporting libraries"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Components within open-dis repos"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Coordinate conversion, PDU utilities, and helper libraries for DIS interoperability."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["coordinate-conversion", "pdu-validation", "simulation-interop"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check for local open-dis dependencies without external network usage."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        configured_path = self._env(self._LOCAL_MIRROR_ENV)
        if configured_path:
            return Path(configured_path).expanduser().exists()

        module_available = any(importlib.util.find_spec(name) is not None for name in self._TOOL_MODULES)
        command_available = any(shutil.which(command) is not None for command in self._TOOL_COMMANDS)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Process DIS support requests or serve deterministic fixture data offline."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "coordinate_convert").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning offline fixture for tactical DIS interoperability workflow.")
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

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "open-dis supporting libraries are not available on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Runtime handoff prepared for local DIS helper execution.",
        }
