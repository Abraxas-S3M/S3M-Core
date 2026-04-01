"""Dataminr adapter with fixture-backed real-time alert shell."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import DataminrConfig
from .normalizer import DataminrNormalizer


class DataminrAdapter(ProviderAdapter):
    provider_id = "osint-dataminr"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = DataminrConfig()
        self.normalizer = DataminrNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "osint-dataminr" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="PREMIUM",
            auth_type="oauth2",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["DATAMINR_CLIENT_ID", "DATAMINR_CLIENT_SECRET"],
            description="Dataminr real-time premium alert adapter for operational awareness.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "alerts_gulf.json").exists()
        return bool(self._env("DATAMINR_CLIENT_ID") and self._env("DATAMINR_CLIENT_SECRET"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def get_alerts(self, watchlist: str | None = None, since: str | None = None, limit: int = 50) -> dict[str, Any]:
        payload = self._load_fixture("alerts_gulf.json") if self.is_airgapped else {"alerts": []}
        alerts = payload.get("alerts", [])
        if watchlist:
            alerts = [a for a in alerts if str(a.get("watchlistName", "")).lower() == watchlist.lower()]
        if since:
            alerts = [a for a in alerts if str(a.get("eventTime", "")) >= since]
        return {"alerts": alerts[:limit], "count": len(alerts[:limit])}

    def get_flash_alerts(self, since: str | None = None) -> dict[str, Any]:
        all_alerts = self.get_alerts(since=since, limit=200)
        flash = [a for a in all_alerts.get("alerts", []) if str(a.get("alertType")) == "flash"]
        return {"alerts": flash, "count": len(flash)}

    def search_historical(self, query: str, date_from: str, date_to: str, limit: int = 100) -> dict[str, Any]:
        all_alerts = self.get_alerts(limit=500)
        filtered = []
        for alert in all_alerts.get("alerts", []):
            caption = str(alert.get("caption", "")).lower()
            if query.lower() in caption and date_from <= str(alert.get("eventTime", "")) <= date_to:
                filtered.append(alert)
        return {"alerts": filtered[:limit], "count": len(filtered[:limit]), "query": query}

    def list_watchlists(self) -> list[dict[str, Any]]:
        payload = self._load_fixture("watchlists.json") if self.is_airgapped else {"watchlists": []}
        return list(payload.get("watchlists", []))

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "alerts"))
        if endpoint == "flash":
            return self.get_flash_alerts(params.get("since"))
        if endpoint == "historical":
            return self.search_historical(
                str(params.get("query", "maritime")),
                str(params.get("date_from", "2024-06-01T00:00:00Z")),
                str(params.get("date_to", datetime.now(timezone.utc).isoformat())),
                int(params.get("limit", 100)),
            )
        if endpoint == "watchlists":
            return self.list_watchlists()
        if endpoint == "alerts":
            return self.get_alerts(params.get("watchlist"), params.get("since"), int(params.get("limit", 50)))
        return self.get_alerts(limit=50)

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "alerts" in raw_data:
            events = []
            for alert in raw_data.get("alerts", []):
                event = self.normalizer.normalize_alert(alert)
                events.append({"event": event, "severity": self.normalizer.severity_from_alert_type(str(alert.get("alertType", "alert")))})
            return {"events": events, "count": len(events)}
        if isinstance(raw_data, list):
            return raw_data
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture alerts and watchlists available" if self.is_airgapped else "oauth credential check",
        }
