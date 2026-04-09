"""TheHive integration adapter.

Military/tactical context:
This adapter standardizes cyber-defense telemetry and response actions so mission
operators can execute defensive workflows in degraded or contested environments.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ThehiveAdapter(IntegrationAdapter):
    """Thin wrapper for TheHive cyber-defense workflows."""

    integration_id = "thehive"
    domain = "cyber"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata needed for tactical adapter discovery."""
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}
        return IntegrationManifest(
            name=str(raw.get("name") or self.integration_id),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description=str(raw.get("description") or "Security incident response platform adapter for orchestrating cyber case management in defensive operations."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities", ["cyber_defense", "incident_response"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw.get("docker_dependencies", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Confirm local tool prerequisites before tactical cyber execution."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return bool(
            any(shutil.which(tool) for tool in ("thehive", "thehive4"))
        or bool(self._env("THEHIVE_URL"))
        or Path("/etc/thehive/application.conf").exists()
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute or emulate the integration action for mission cyber defense."""
        request = params or {}
        if self.is_airgapped:
            return {
                "status": "ok",
                "mode": "airgapped",
                "integration_id": self.integration_id,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "mode": "online",
                "integration_id": self.integration_id,
                "error": "required tooling not detected",
                "request": request,
            }

        action = str(request.get("action") or "create_incident_case")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "action": action,
            "request": request,
            "detail": "Live execution must be wired by platform operators in the deployment environment.",
        }
