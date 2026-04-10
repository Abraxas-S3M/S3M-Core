"""AI-powered predictive maintenance adapter for tactical vehicle sustainment."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AiPoweredPredictiveMaintenanceAdapter(IntegrationAdapter):
    """Wrap gradient-boosting maintenance prediction for sovereign vehicle fleets."""

    integration_id = "ai-powered-predictive-maintenance-system"
    domain = "maintenance"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("ai-powered-predictive-maintenance-system manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for tactical maintenance model orchestration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "AI-Powered-Predictive-Maintenance-System-for-Vehicles"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/Siddhartha80/AI-Powered-Predictive-Maintenance-System-for-Vehicles"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Gradient boosting predictive maintenance wrapper for vehicle readiness forecasting."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["real_time_health_scoring", "failure_risk_prediction", "maintenance_visualization"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local model assets for airgapped tactical maintenance support."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("AI_POWERED_PREDICTIVE_MAINTENANCE_SYSTEM_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(
            shutil.which(command)
            for command in (
                "ai-powered-predictive-maintenance-system",
                "vehicle-predictive-maintenance-cli",
            )
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute predictive-maintenance operation with deterministic offline fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError(
                "ai-powered-predictive-maintenance-system execute params must be a dictionary."
            )

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError(
                    "Missing ai-powered-predictive-maintenance-system fixture: sample_response.json"
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
                "error": "ai-powered-predictive-maintenance-system runtime not detected.",
            }

        operation = str(request.get("operation") or "vehicle_failure_risk_assessment")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "operation": operation,
            "request": request,
            "detail": "Live model execution is deployment-specific and intentionally stubbed.",
        }
