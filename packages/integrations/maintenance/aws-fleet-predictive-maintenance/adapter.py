"""AWS fleet predictive maintenance adapter for tactical sustainment forecasting."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwsFleetPredictiveMaintenanceAdapter(IntegrationAdapter):
    """Wrap predictive maintenance inference for sovereign fleet readiness planning."""

    integration_id = "aws-fleet-predictive-maintenance"
    domain = "maintenance"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("aws-fleet-predictive-maintenance manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for tactical predictive-maintenance capability discovery."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "aws-fleet-predictive-maintenance"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/awslabs/aws-fleet-predictive-maintenance"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Deep learning predictive maintenance for fleet failure forecasting."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["failure_prediction", "downtime_reduction", "maintenance_prioritization"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local model execution prerequisites for disconnected deployments."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("AWS_FLEET_PREDICTIVE_MAINTENANCE_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(
            shutil.which(command)
            for command in ("aws-fleet-predictive-maintenance", "predictive-maintenance-cli")
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute predictive maintenance workflow with airgapped fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("aws-fleet-predictive-maintenance execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError(
                    "Missing aws-fleet-predictive-maintenance fixture: sample_response.json"
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
                "error": "aws-fleet-predictive-maintenance runtime not detected.",
            }

        operation = str(request.get("operation") or "predictive_maintenance_inference")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "operation": operation,
            "request": request,
            "detail": "Live model execution is deployment-specific and intentionally stubbed.",
        }
