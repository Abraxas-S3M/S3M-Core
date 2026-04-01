"""GDELT adapter for OSINT global event and media monitoring."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import GDELTConfig
from .normalizer import GDELT_COLUMNS, GDELTNormalizer


class GDELTAdapter(ProviderAdapter):
    provider_id = "osint-gdelt"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = GDELTConfig()
        self.normalizer = GDELTNormalizer()
        self.fixture_dir = Path(__file__).resolve().parent / "fixtures"
        if not self.fixture_dir.exists():
            self.fixture_dir = Path(__file__).resolve().parents[1] / "osint-gdelt" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="FREE",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description="GDELT media and geocoded conflict telemetry with CAMEO coding.",
        )

    def validate_credentials(self) -> bool:
        # Tactical context: no auth means field kits validate local cache viability in denied networks.
        if self.is_airgapped:
            return (self.fixture_dir / "articles_response.json").exists() and (self.fixture_dir / "cameo_events_sample.csv").exists()
        return True

    def _http_get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        query = parse.urlencode(params, doseq=True)
        with request.urlopen(f"{url}?{query}", timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_articles(self, query: str, timespan: str = "24h", max_records: int = 50) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "articles_response.json")
            payload["query"] = query
            return payload
        return self._http_get_json(
            self.config.doc_api_url,
            {
                "query": query,
                "mode": "artlist",
                "maxrecords": max_records,
                "format": "json",
                "timespan": timespan,
            },
        )

    def fetch_geo_events(self, query: str, timespan: str = "24h") -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "geo_response.json")
            payload["query"] = query
            return payload
        return self._http_get_json(
            self.config.geo_api_url,
            {
                "query": query,
                "format": "geojson",
                "timespan": timespan,
            },
        )

    def _download_cameo_csv(self, date_code: str) -> str:
        if self.is_airgapped:
            return self._read_text(self.fixture_dir / "cameo_events_sample.csv")
        url = f"{self.config.events_csv_base_url}/{date_code}.export.CSV.zip"
        with request.urlopen(url, timeout=30) as response:
            zipped_bytes = response.read()
        with zipfile.ZipFile(io.BytesIO(zipped_bytes), "r") as zf:
            inner = zf.namelist()[0]
            return zf.read(inner).decode("utf-8", errors="replace")

    def fetch_cameo_events(self, date: str | None = None, country_codes: list[str] | None = None) -> dict[str, Any]:
        date_code = date or datetime.now(timezone.utc).strftime("%Y%m%d")
        csv_content = self._download_cameo_csv(date_code)
        events = self.normalizer.parse_cameo_csv(
            csv_content=csv_content,
            filter_countries=country_codes,
            filter_codes=self.config.cameo_conflict_prefixes,
        )
        return {"events": events, "count": len(events), "date": date_code}

    def search_saudi_topics(self) -> dict[str, Any]:
        topics: dict[str, Any] = {}
        for topic, query in self.config.saudi_queries.items():
            payload = self.fetch_articles(query=query, timespan=self.config.default_timespan, max_records=50)
            articles = payload.get("articles", [])
            tone_values = [float(item.get("tone", 0.0) or 0.0) for item in articles]
            avg_tone = (sum(tone_values) / len(tone_values)) if tone_values else 0.0
            topics[topic] = {
                "query": query,
                "article_count": len(articles),
                "avg_tone": round(avg_tone, 3),
            }
        return {"topics": topics, "count": len(topics)}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        action = params.get("action", "cameo")
        if action == "articles":
            return self.fetch_articles(
                query=str(params.get("query", "saudi arabia")),
                timespan=str(params.get("timespan", self.config.default_timespan)),
                max_records=int(params.get("max_records", 50)),
            )
        if action == "geo":
            return self.fetch_geo_events(
                query=str(params.get("query", "middle east conflict")),
                timespan=str(params.get("timespan", self.config.default_timespan)),
            )
        if action == "saudi_topics":
            return self.search_saudi_topics()
        if action == "cameo_csv_raw":
            date_code = str(params.get("date") or datetime.now(timezone.utc).strftime("%Y%m%d"))
            content = self._download_cameo_csv(date_code)
            return {"csv": content, "columns": list(GDELT_COLUMNS), "date": date_code}
        return self.fetch_cameo_events(
            date=params.get("date"),
            country_codes=params.get("country_codes"),
        )

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "articles" in raw_data:
            return [self.normalizer.normalize_article(item) for item in raw_data.get("articles", [])]
        if raw_data.get("type") == "FeatureCollection":
            return [self.normalizer.normalize_geo_feature(feature) for feature in raw_data.get("features", [])]
        if "events" in raw_data:
            return [self.normalizer.normalize_cameo_event(item) for item in raw_data.get("events", [])]
        return []

    def health_check(self) -> dict[str, Any]:
        try:
            if self.is_airgapped:
                ok = self.validate_credentials()
                return {
                    "status": "ok" if ok else "degraded",
                    "latency_ms": 1.0,
                    "last_successful_fetch": None,
                    "error_count": 0,
                    "detail": "air-gapped fixture check",
                }
            sample = self.fetch_articles(query="saudi", timespan="1d", max_records=1)
            count = len(sample.get("articles", []))
            return {
                "status": "ok",
                "latency_ms": 100.0,
                "last_successful_fetch": datetime.now(timezone.utc) - timedelta(seconds=5),
                "error_count": 0,
                "detail": f"sample query returned {count} article(s)",
            }
        except Exception as exc:  # pragma: no cover
            return {
                "status": "failing",
                "latency_ms": None,
                "last_successful_fetch": None,
                "error_count": 1,
                "detail": str(exc),
            }
