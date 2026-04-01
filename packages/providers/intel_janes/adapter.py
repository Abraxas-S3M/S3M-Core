"""Janes intelligence adapter with fixture-based premium integrations."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import JanesConfig
from .normalizer import JanesNormalizer


class JanesAdapter(ProviderAdapter):
    provider_id = "intel-janes"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = JanesConfig()
        self.normalizer = JanesNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "intel-janes" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="PREMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["JANES_API_KEY"],
            description="Janes premium defense intelligence for ORBAT/equipment/threat enrichment.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "equipment_f15sa.json").exists()
        return bool(self._env("JANES_API_KEY"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def search_equipment(self, query: str, country: str | None = None) -> dict[str, Any]:
        payload = self._load_fixture("equipment_f15sa.json") if self.is_airgapped else {}
        payload["query"] = query
        if country:
            payload["country"] = country
        return payload

    def get_country_military(self, country_code: str = "SA") -> dict[str, Any]:
        payload = self._load_fixture("country_saudi_military.json") if self.is_airgapped else {}
        payload["country_code"] = country_code
        return payload

    def get_threat_assessment(self, region: str = "middle-east") -> dict[str, Any]:
        payload = self._load_fixture("threat_assessment_mena.json") if self.is_airgapped else {}
        payload["region"] = region
        return payload

    def get_orbat(self, country_code: str = "SA") -> dict[str, Any]:
        payload = self._load_fixture("orbat_saudi.json") if self.is_airgapped else {}
        payload["country_code"] = country_code
        return payload

    def get_defense_news(self, region: str = "middle-east", days_back: int = 7) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "articles": [
                {
                    "id": "JANES-NEWS-001",
                    "title": "Regional integrated air defense drill announced",
                    "publisher": "Janes",
                    "region": region,
                    "country": "SA",
                    "published_at": (now - timedelta(days=min(days_back, 2))).isoformat(),
                    "sentiment_score": -0.25,
                }
            ],
            "count": 1,
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "equipment"))
        if endpoint == "country":
            return self.get_country_military(str(params.get("country_code", "SA")))
        if endpoint == "threat":
            return self.get_threat_assessment(str(params.get("region", "middle-east")))
        if endpoint == "orbat":
            return self.get_orbat(str(params.get("country_code", "SA")))
        if endpoint == "news":
            return self.get_defense_news(str(params.get("region", "middle-east")), int(params.get("days_back", 7)))
        return self.search_equipment(str(params.get("query", "F-15SA")), params.get("country"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "specifications" in raw_data and "performance" in raw_data:
            return self.normalizer.normalize_equipment(raw_data)
        if isinstance(raw_data, dict) and "units" in raw_data and "branches" in raw_data:
            return self.normalizer.normalize_orbat(raw_data)
        if isinstance(raw_data, dict) and "assessment" in raw_data:
            assessment = dict(raw_data)
            assessment["id"] = assessment.get("id", "JANES-THREAT-001")
            return self.normalizer.normalize_threat(assessment)
        if isinstance(raw_data, dict) and "articles" in raw_data:
            return [self.normalizer.normalize_news(article) for article in raw_data.get("articles", [])]
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture defense intel available" if self.is_airgapped else "api key check",
        }
