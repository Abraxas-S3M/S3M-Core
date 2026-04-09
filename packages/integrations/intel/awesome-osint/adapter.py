"""Adapter for awesome-osint intelligence workflows.

Military/tactical context:
This wrapper standardizes OSINT and intelligence briefing handoff so command
staff can run repeatable assessments in sovereign, airgapped environments.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeOsintAdapter(IntegrationAdapter):
    """S3M adapter for awesome-osint intelligence briefing operations."""

    integration_id = "awesome-osint"
    domain = "intel"

    _repo_env_var = "INTEL_AWESOME_OSINT_PATH"
    _module_hints = ('yaml',)
    _binary_hints = ('git',)
    _default_operation = "resource_curation_brief"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(f"s3m.integrations.intel.{self.integration_id}")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate request payloads before mission-system processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")

        # Tactical safety: normalize to JSON-safe primitives for deterministic replay.
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}

        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-osint"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/jivoi/awesome-osint"),
            license=str(raw.get("license") or "Unknown"),
            description=str(raw.get("description") or "Curated list of open-source intelligence tools and references for mission planning workflows."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ['resource_curation', 'osint_training_support', 'tool_reference_briefing']),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local dependencies for disconnected intelligence operations."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        configured_path = self._env(self._repo_env_var)
        if configured_path:
            return Path(configured_path).expanduser().exists()

        module_available = any(importlib.util.find_spec(name) is not None for name in self._module_hints)
        command_available = any(shutil.which(command) is not None for command in self._binary_hints)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper logic and return fixtures for airgapped deployments."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._default_operation)

        if self.is_airgapped:
            self.logger.info("Returning %s fixture payload for tactical briefing.", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "data": self._read_fixture("sample_response.json"),
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
                "message": "Required local dependencies are unavailable for this intelligence adapter.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Adapter validated local dependencies and is ready for orchestrator handoff.",
        }
