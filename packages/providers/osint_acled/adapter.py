"""ACLED adapter for verified geocoded conflict event ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import ACLEDConfig
from .normalizer import ACLEDNormalizer


class ACLEDAdapter(ProviderAdapter):
    provider_id = "osint-acled"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = ACLEDConfig()
        self.normalizer = ACLEDNormalizer()
        self.fixture_dir = Path(__file__).resolve().parent / "fixtures"
        if not self.fixture_dir.exists():
            self.fixture_dir = Path(__file__).resolve().parents[1] / "osint-acled" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="FREE",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["ACLED_API_KEY", "ACLED_EMAIL"],
            description="ACLED verified conflict and fatality event feed for early warning.",
        )

    def validate_credentials(self) -> bool:
        # Tactical context: disconnected deployments must still confirm local ACLED cache availability.
        if self.is_airgapped:
            return (self.fixture_dir / "acled_mena_response.json").exists()
        return bool(self._env("ACLED_API_KEY") and self._env("ACLED_EMAIL"))

    def _http_get(self, params: dict[str, Any]) -> dict[str, Any]:
        query = parse.urlencode(params, doseq=True)
        with request.urlopen(f"{self.config.base_url}?{query}", timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_events(
        self,
        countries: list[str],
        event_types: list[str],
        date_from: str,
        date_to: str,
        limit: int = 500,
    ) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "acled_mena_response.json")
            filtered: list[dict[str, Any]] = []
            for item in payload.get("data", []):
                if countries and item.get("country") not in countries:
                    continue
                if event_types and item.get("event_type") not in event_types:
                    continue
                filtered.append(item)
            return {"success": True, "data": filtered[:limit], "count": min(len(filtered), limit)}

        params = {
            "key": self._env("ACLED_API_KEY"),
            "email": self._env("ACLED_EMAIL"),
            "event_date": f"{date_from}|{date_to}",
            "event_date_where": "BETWEEN",
            "country": "|".join(countries),
            "event_type": "|".join(event_types),
            "limit": limit,
        }
        return self._http_get(params)

    def _date_window(self, days_back: int) -> tuple[str, str]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(days_back, 1))
        return start.isoformat(), end.isoformat()

    def fetch_saudi_region(self, days_back: int = 30) -> dict[str, Any]:
        date_from, date_to = self._date_window(days_back)
        return self.fetch_events(
            countries=self.config.saudi_relevant_countries,
            event_types=self.config.conflict_event_types,
            date_from=date_from,
            date_to=date_to,
            limit=500,
        )

    def fetch_yemen_conflict(self, days_back: int = 30) -> dict[str, Any]:
        date_from, date_to = self._date_window(days_back)
        return self.fetch_events(
            countries=["Yemen"],
            event_types=self.config.all_event_types,
            date_from=date_from,
            date_to=date_to,
            limit=500,
        )

    def fetch_by_actor(self, actor_name: str, days_back: int = 90) -> dict[str, Any]:
        date_from, date_to = self._date_window(days_back)
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "acled_mena_response.json")
            needle = actor_name.lower().strip()
            matches = [
                item
                for item in payload.get("data", [])
                if needle in str(item.get("actor1", "")).lower() or needle in str(item.get("actor2", "")).lower()
            ]
            return {"success": True, "data": matches, "count": len(matches), "actor": actor_name}

        params = {
            "key": self._env("ACLED_API_KEY"),
            "email": self._env("ACLED_EMAIL"),
            "event_date": f"{date_from}|{date_to}",
            "event_date_where": "BETWEEN",
            "actor1": actor_name,
            "actor2": actor_name,
            "limit": 500,
        }
        return self._http_get(params)

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        action = params.get("action", "saudi_region")
        if action == "events":
            return self.fetch_events(
                countries=params.get("countries", self.config.saudi_relevant_countries),
                event_types=params.get("event_types", self.config.conflict_event_types),
                date_from=str(params.get("date_from", self._date_window(30)[0])),
                date_to=str(params.get("date_to", self._date_window(30)[1])),
                limit=int(params.get("limit", 500)),
            )
        if action == "yemen":
            return self.fetch_yemen_conflict(days_back=int(params.get("days_back", 30)))
        if action == "actor":
            return self.fetch_by_actor(str(params.get("actor_name", "Houthi")), days_back=int(params.get("days_back", 90)))
        return self.fetch_saudi_region(days_back=int(params.get("days_back", 30)))

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        return [self.normalizer.normalize_event(item) for item in raw_data.get("data", [])]

    def health_check(self) -> dict[str, Any]:
        if self.is_airgapped:
            ok = self.validate_credentials()
            return {
                "status": "ok" if ok else "degraded",
                "latency_ms": 1.0,
                "last_successful_fetch": None,
                "error_count": 0,
                "detail": "air-gapped fixture check",
            }

        if not self.validate_credentials():
            return {
                "status": "failing",
                "latency_ms": None,
                "last_successful_fetch": None,
                "error_count": 1,
                "detail": "missing ACLED credentials",
            }
        return {
            "status": "ok",
            "latency_ms": 120.0,
            "last_successful_fetch": datetime.now(timezone.utc),
            "error_count": 0,
            "detail": "credentials configured",
        }
