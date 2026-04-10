"""MilitaryAssetManagementSystem adapter for tactical asset sustainment workflows."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryassetmanagementsystemAdapter(IntegrationAdapter):
    """Wrap MilitaryAssetManagementSystem for sovereign military asset maintenance."""

    integration_id = "militaryassetmanagementsystem"
    domain = "maintenance"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("MilitaryAssetManagementSystem manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata for tactical procurement and maintenance orchestration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "MilitaryAssetManagementSystem"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/chiragSahani/MilitaryAssetManagementSystem"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Secure military asset management and role-based sustainment dashboards."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["asset_inventory", "maintenance_status", "role_based_operations"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime readiness for disconnected maintenance operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("MILITARYASSETMANAGEMENTSYSTEM_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(
            shutil.which(command)
            for command in ("military-asset-management", "mams-cli", "asset-management-cli")
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a maintenance action with fixture fallback for sovereign contingencies."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("MilitaryAssetManagementSystem execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError(
                    "Missing MilitaryAssetManagementSystem fixture: sample_response.json"
                )
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
                "error": "MilitaryAssetManagementSystem runtime not detected.",
            }

        operation = str(request.get("operation") or "asset_status_overview")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "operation": operation,
            "request": request,
            "detail": "Live execution is deployment-specific and intentionally stubbed in S3M.",
        }
