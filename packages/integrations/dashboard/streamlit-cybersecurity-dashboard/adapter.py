"""Streamlit cybersecurity dashboard integration adapter.

Military/tactical context:
This adapter provides a controlled path to threat and vulnerability visual
snapshots used by mission cyber defense teams in offline deployments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class StreamlitCybersecurityDashboardAdapter(IntegrationAdapter):
    """Adapter wrapper for the Streamlit cybersecurity dashboard repository."""

    integration_id = "streamlit-cybersecurity-dashboard"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.dashboard.streamlit-cybersecurity-dashboard"
        )

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_dict(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load manifest metadata for streamlit dashboard integration."""
        raw = self._manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Streamlit-Cybersecurity-Dashboard"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/ajitagupta/streamlit-cybersecurity-dashboard"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Interactive dashboards for security threats and incident monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities")),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Confirm local runtime support for streamlit dashboard workflows."""
        fixture_ready = bool(self._read_fixture("sample_response.json"))
        command_ready = any(
            shutil.which(command) for command in ("streamlit", "python3", "python")
        )
        return fixture_ready if self.is_airgapped else command_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper and return fixture data under airgapped posture."""
        if params is None:
            safe_params: dict[str, Any] = {}
        elif isinstance(params, dict):
            safe_params = params
        else:
            raise ValueError(
                "Streamlit-Cybersecurity-Dashboard execute params must be a dictionary."
            )
        operation = str(safe_params.get("operation") or "incident-overview")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "data": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "status": "unavailable",
                "error": "Streamlit dashboard runtime is not available on this node.",
            }

        # Sovereign policy: adapter does not open external dashboard sessions.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "status": "ready",
            "message": "Local runtime validated; remote dashboard invocation is disabled by policy.",
        }
