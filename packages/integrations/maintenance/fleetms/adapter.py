"""fleetms adapter for tactical fleet sustainment and readiness tracking."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class FleetmsAdapter(IntegrationAdapter):
    """Wrap fleetms for military vehicle maintenance scheduling and tracking."""

    integration_id = "fleetms"
    domain = "maintenance"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("fleetms manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata used to register fleet maintenance capabilities in S3M."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "fleetms"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/jmnda-dev/fleetms"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Open-source fleet maintenance scheduler and tracking wrapper for mission vehicles."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["maintenance_scheduling", "fleet_tracking", "work_order_planning"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm local fleetms tooling exists for sovereign logistics operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("FLEETMS_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("fleetms", "fleetms-cli"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute fleet maintenance workflow with tactical offline fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("fleetms execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing fleetms fixture: sample_response.json")
            return {
                "status": "ok",
                "mode": "airgapped",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "source": "fixture",
                "request": request,
                "result": fixture,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "mode": "online",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "request": request,
                "error": "fleetms runtime not detected.",
            }

        operation = str(request.get("operation") or "fleet_maintenance_summary")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "operation": operation,
            "request": request,
            "detail": "Live fleetms execution is deployment-specific and intentionally stubbed.",
        }
