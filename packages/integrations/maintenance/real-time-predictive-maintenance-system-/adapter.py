"""Aircraft predictive maintenance adapter for tactical sortie reliability."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RealTimePredictiveMaintenanceAdapter(IntegrationAdapter):
    """Wrap aircraft engine predictive maintenance for sovereign air operations."""

    integration_id = "real-time-predictive-maintenance-system-"
    domain = "maintenance"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError(
                "real-time-predictive-maintenance-system- manifest must be a YAML mapping."
            )
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for tactical aircraft-maintenance mission orchestration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Real-Time-Predictive-Maintenance-System-for-Aircraft"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/EkeminiThompson/Real-Time-Predictive-Maintenance-System-for-Aircraft"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Real-time aircraft engine maintenance prediction and sustainment dashboard."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[
                str(item)
                for item in raw.get("capabilities")
                or ["aircraft_engine_monitoring", "anomaly_detection", "sortie_risk_forecasting"]
            ],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local predictive-maintenance tooling for disconnected airbases."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("REAL_TIME_PREDICTIVE_MAINTENANCE_SYSTEM_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(
            shutil.which(command)
            for command in (
                "real-time-predictive-maintenance-system",
                "aircraft-predictive-maintenance-cli",
            )
        )

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute aircraft maintenance action with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError(
                "real-time-predictive-maintenance-system- execute params must be a dictionary."
            )

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError(
                    "Missing real-time-predictive-maintenance-system- fixture: sample_response.json"
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
                "error": "real-time-predictive-maintenance-system- runtime not detected.",
            }

        operation = str(request.get("operation") or "aircraft_health_prediction")
        return {
            "status": "accepted",
            "mode": "online",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "operation": operation,
            "request": request,
            "detail": "Live execution is deployment-specific and intentionally stubbed.",
        }
