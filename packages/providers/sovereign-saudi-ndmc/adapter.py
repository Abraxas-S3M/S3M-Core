"""Formal Saudi NDMC sovereign compliance adapter over weather ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import SovereignNDMCConfig
from .normalizer import SovereignNDMCNormalizer


class SovereignNDMCAdapter(ProviderAdapter):
    def __init__(self, config: SovereignNDMCConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or SovereignNDMCConfig()
        self.normalizer = SovereignNDMCNormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _incoming_dir(self) -> Path:
        return Path(self.config.chunk5_incoming_dir)

    def _has_gov_credentials(self) -> bool:
        api_key = os.getenv("S3M_NDMC_GOV_API_KEY") or os.getenv("NDMC_GOV_API_KEY")
        cert = os.getenv("S3M_NDMC_GOV_CLIENT_CERT") or os.getenv("NDMC_GOV_CLIENT_CERT")
        return bool(api_key or cert)

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="sovereign-saudi-ndmc",
            name="Saudi NDMC Sovereign Government Weather",
            category=ProviderCategory.SOVEREIGN_REGIONAL,
            tier=ProviderTier.GOVERNMENT,
            base_url=self.config.government_api_url,
            auth_type="certificate",
            rate_limit_rpm=self.config.rate_limit_rpm,
            supported_schemas=["NormalizedWeatherObservation"],
            required_env_vars=[],
            optional_env_vars=["NDMC_GOV_API_KEY", "NDMC_GOV_CLIENT_CERT"],
            description="Government compliance and data-sharing layer wrapping Saudi NDMC weather ingestion.",
            docs_url="https://ncm.gov.sa",
            airgap_capable=True,
            enabled=True,
            tags=["saudi", "ndmc", "weather", "sovereign", "government"],
        )

    def validate_credentials(self) -> bool:
        if self._has_gov_credentials() and self.mode != "airgapped":
            return True
        if self._incoming_dir().exists():
            return True
        return (self._fixture_dir() / "fixtures" / "official_alerts_gov.json").exists()

    def get_official_alerts(self) -> dict[str, Any]:
        payload = self._load_fixture_json("official_alerts_gov.json")
        alerts = [self.normalizer.normalize_official_alert(a) for a in payload.get("alerts", [])]
        # Tactical context: sovereign alerts outrank commercial feeds during mission planning.
        return {
            "alerts": alerts,
            "classification": self.config.data_classification,
            "authority": "Saudi National Center of Meteorology (NCM)",
            "primary_language": "ar",
        }

    def get_military_weather_advisory(self, region: str | None = None) -> dict[str, Any]:
        payload = self._load_fixture_json("military_advisory.json")
        advisory = self.normalizer.normalize_military_advisory(payload.get("advisory", {}))
        if region:
            advisory["region"] = region
        return {"advisory": advisory}

    def get_data_sharing_status(self) -> dict[str, Any]:
        payload = self._load_fixture_json("data_sharing_status.json")
        freshness = float(payload.get("data_freshness_hours", 999.0))
        if freshness <= 3:
            sla = "compliant"
        elif freshness <= 6:
            sla = "degraded"
        else:
            sla = "non_compliant"
        payload["sla_status"] = sla
        return payload

    def verify_data_classification(self, data: dict[str, Any]) -> dict[str, Any]:
        marking = str(data.get("classification", "")).strip()
        classified = marking == self.config.data_classification
        return {
            "classified": classified,
            "marking": marking or self.config.data_classification,
            "handling_instructions": "Official Use — GCC redistribution with approval",
        }

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        endpoint = params.get("endpoint", "official_alerts")
        if endpoint == "official_alerts":
            return self.get_official_alerts()
        if endpoint == "military_advisory":
            return self.get_military_weather_advisory(region=params.get("region"))
        if endpoint == "data_sharing":
            return self.get_data_sharing_status()
        return self.get_official_alerts()

    def normalize(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        if "alerts" in raw_data:
            return [self.normalizer.normalize_official_alert(a) for a in raw_data.get("alerts", [])]
        if "advisory" in raw_data:
            return [self.normalizer.normalize_military_advisory(raw_data.get("advisory", {}))]
        return []

    def health_check(self) -> dict[str, Any]:
        sharing = self.get_data_sharing_status()
        return {
            "status": "ok" if self.validate_credentials() else "degraded",
            "detail": {
                "mode": self.mode,
                "last_data_received": sharing.get("last_data_received", datetime.now(timezone.utc).isoformat()),
                "sla_status": sharing.get("sla_status", "unknown"),
            },
        }
