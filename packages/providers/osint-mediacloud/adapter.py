"""Media Cloud adapter for narrative and media trend monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import MediaCloudConfig
from .normalizer import MediaCloudNormalizer


class MediaCloudAdapter(ProviderAdapter):
    provider_id = "osint-mediacloud"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = MediaCloudConfig()
        self.normalizer = MediaCloudNormalizer()
        self.fixture_dir = Path(__file__).resolve().parent / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="FREE",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["S3M_MEDIACLOUD_API_KEY"],
            description="Media Cloud narrative analysis and story-volume telemetry.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "stories_response.json").exists()
        return bool(self._env("MEDIACLOUD_API_KEY"))

    def _api_get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        key = self._env("MEDIACLOUD_API_KEY")
        if not key:
            raise RuntimeError("Missing MEDIACLOUD_API_KEY")
        query = dict(params)
        query["key"] = key
        encoded = parse.urlencode(query, doseq=True)
        with request.urlopen(f"{self.config.base_url}{endpoint}?{encoded}", timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_stories(self, query: str, days_back: int = 7, limit: int = 100) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "stories_response.json")
            payload["query"] = query
            return payload
        start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        return self._api_get(
            "/stories_public/list",
            {
                "q": query,
                "fq": f"publish_date:[{start} TO *]",
                "rows": min(limit, self.config.max_rows),
            },
        )

    def fetch_story_count_timeseries(self, query: str, days_back: int = 30, period: str = "day") -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "count_timeseries.json")
            payload["query"] = query
            return payload
        return self._api_get(
            "/stories_public/count",
            {
                "q": query,
                "split": "true",
                "split_period": period,
                "fq": f"publish_date:[NOW-{days_back}DAYS TO NOW]",
            },
        )

    def fetch_word_frequency(self, query: str) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "word_frequency.json")
            payload["query"] = query
            return payload
        return self._api_get("/wc/list", {"q": query})

    def compare_arabic_english(self, query: str, days_back: int = 7) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "arabic_english_comparison.json")
            payload["query"] = query
            return payload

        start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        arabic_counts = self._api_get(
            "/stories_public/count",
            {
                "q": query,
                "split": "false",
                "fq": f"publish_date:[{start} TO *] AND media_sets_id:{self.config.arabic_media_collection_id}",
            },
        )
        english_counts = self._api_get(
            "/stories_public/count",
            {
                "q": query,
                "split": "false",
                "fq": f"publish_date:[{start} TO *] AND language:en",
            },
        )
        arabic_words = self.fetch_word_frequency(f"{query} AND media_sets_id:{self.config.arabic_media_collection_id}")
        english_words = self.fetch_word_frequency(f"{query} AND language:en")
        a_count = int(arabic_counts.get("count", 0))
        e_count = int(english_counts.get("count", 0))
        ratio = round(a_count / e_count, 3) if e_count else float(a_count)
        return {
            "arabic": {"count": a_count, "top_words": arabic_words.get("word_counts", [])[:10]},
            "english": {"count": e_count, "top_words": english_words.get("word_counts", [])[:10]},
            "coverage_ratio": ratio,
        }

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        action = params.get("action", "stories")
        if action == "count":
            return self.fetch_story_count_timeseries(
                query=str(params.get("query", "saudi security")),
                days_back=int(params.get("days_back", 30)),
                period=str(params.get("period", "day")),
            )
        if action == "words":
            return self.fetch_word_frequency(query=str(params.get("query", "saudi defense")))
        if action == "compare":
            return self.compare_arabic_english(query=str(params.get("query", "yemen houthi")), days_back=int(params.get("days_back", 7)))
        return self.fetch_stories(
            query=str(params.get("query", "gulf security")),
            days_back=int(params.get("days_back", 7)),
            limit=int(params.get("limit", self.config.default_rows)),
        )

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "stories" in raw_data:
            return [self.normalizer.normalize_story(item) for item in raw_data.get("stories", [])]
        return []

    def health_check(self) -> dict[str, Any]:
        if self.is_airgapped:
            return {
                "status": "ok" if self.validate_credentials() else "degraded",
                "latency_ms": 1.0,
                "last_successful_fetch": None,
                "error_count": 0,
                "detail": "air-gapped fixture check",
            }
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency_ms": 80.0,
            "last_successful_fetch": datetime.now(timezone.utc),
            "error_count": 0 if ok else 1,
            "detail": "api key available" if ok else "missing api key",
        }
