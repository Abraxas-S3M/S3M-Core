"""Fleetbase adapter for tactical logistics and sustainment dashboards."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class FleetbaseAdapter(IntegrationAdapter):
    """Wraps Fleetbase for mission sustainment workflows and convoy monitoring."""

    integration_id = "fleetbase"
    domain = "dashboard"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Fleetbase manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for tactical logistics dashboard registration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Fleetbase"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/fleetbase/fleetbase"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "Modular logistics dashboard for sustainment workflows, convoys, and monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities") or ["convoy_tracking", "workflow_monitoring"]],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm local Fleetbase runtime is present for sovereign deployments."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("FLEETBASE_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("fleetbase", "fleetbase-cli"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute logistics dashboard operation with fixture fallback in airgapped mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("Fleetbase execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing Fleetbase fixture: sample_response.json")
            response = dict(fixture)
            response["mode"] = "airgapped"
            response["request"] = request
            return response

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "detail": "Fleetbase CLI or local checkout path was not found.",
            }

        # Tactical data governance: local execution is intentionally deferred in this wrapper.
        return {
            "status": "deferred",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "request": request,
            "detail": "Local Fleetbase execution is available but intentionally stubbed.",
        }

