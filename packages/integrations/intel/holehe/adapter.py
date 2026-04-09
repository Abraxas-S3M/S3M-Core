"""Adapter for holehe email-account OSINT checks.

Military/tactical context:
Email footprint analysis supports identity resolution and influence-monitoring
operations when analysts require repeatable offline workflows.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class HoleheAdapter(IntegrationAdapter):
    """Expose holehe capability with secure, airgapped fixture execution."""

    integration_id = "holehe"
    domain = "intel"

    _repo_env_var = "HOLEHE_PATH"
    _fallback_binary = "holehe"

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
        """Validate payload shape for sovereign mission safety."""
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
        """Load integration metadata from manifest.yaml."""
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}

        return IntegrationManifest(
            name=str(raw.get("name") or "holehe"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/megadose/holehe"),
            license=str(raw.get("license") or "Unknown"),
            description=str(raw.get("description") or "Check email usage across sites for OSINT."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["email_footprint_check", "account_presence_assessment", "identity_pivot"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Determine if local holehe resources are available."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        configured_path = self._env(self._repo_env_var)
        if configured_path:
            return Path(configured_path).expanduser().exists()
        return shutil.which(self._fallback_binary) is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper behavior and return fixture in denied environments."""
        safe_params = self._sanitize_params(params)

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": safe_params,
                "data": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "available": available,
            "status": "ready" if available else "unavailable",
            "message": (
                "holehe is available for local email footprint checks."
                if available
                else "Install holehe or set HOLEHE_PATH for sovereign deployments."
            ),
            "request": safe_params,
        }
