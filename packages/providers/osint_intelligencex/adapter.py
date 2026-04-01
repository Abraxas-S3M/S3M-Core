"""Intelligence X adapter for deep OSINT search and polling workflows."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import IntelligenceXConfig
from .normalizer import IntelligenceXNormalizer


class IntelligenceXAdapter(ProviderAdapter):
    provider_id = "osint-intelligencex"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = IntelligenceXConfig()
        self.normalizer = IntelligenceXNormalizer()
        self.fixture_dir = Path(__file__).resolve().parent / "fixtures"
        if not self.fixture_dir.exists():
            self.fixture_dir = Path(__file__).resolve().parents[1] / "osint-intelligencex" / "fixtures"

    def _api_key(self) -> str:
        return self._env("INTELLIGENCEX_API_KEY")

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="OSINT_GLOBAL_EVENTS",
            tier="FREEMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["INTELLIGENCEX_API_KEY"],
            description="Intelligence X deep OSINT search for leaks, darknet, and WHOIS history.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "search_results.json").exists() and (self.fixture_dir / "phonebook_results.json").exists()
        if not self._api_key():
            return False
        try:
            result = self.search("test.com", max_results=1, media=0, sort=4)
            return "records" in result
        except Exception:  # pragma: no cover
            return False

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self.is_airgapped:
            raise RuntimeError("Network calls are disabled in air-gapped mode")
        if not self._api_key():
            raise RuntimeError("Missing INTELLIGENCEX_API_KEY")

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "x-key": self._api_key(),
            "content-type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        req = request.Request(
            f"{self.config.base_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def search(self, term: str, max_results: int = 50, media: int = 0, sort: int = 4) -> dict[str, Any]:
        if self.is_airgapped:
            complete = self._read_json(self.fixture_dir / "search_status_complete.json")
            records = complete.get("records", [])
            return {
                "records": records[:max_results],
                "count": min(len(records), max_results),
                "term": term,
                "search_id": str(complete.get("id", "fixture-search")),
            }

        submit = self._request_json(
            "POST",
            "/intelligent/search",
            {
                "term": term,
                "maxresults": min(max_results, self.config.max_results_per_search),
                "media": media,
                "sort": sort,
                "terminate": [],
            },
        )
        search_id = str(submit.get("id"))
        for _ in range(self.config.max_poll_attempts):
            polled = self._request_json("GET", f"/intelligent/search/result?id={parse.quote(search_id)}&limit={max_results}")
            status = int(polled.get("status", 0))
            if status == 2:
                records = polled.get("records", [])
                return {"records": records, "count": len(records), "term": term, "search_id": search_id}
            time.sleep(self.config.poll_interval_seconds)
        return {"records": [], "count": 0, "term": term, "search_id": search_id}

    def search_phonebook(self, term: str, target: int = 1, max_results: int = 100) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "phonebook_results.json")
            selectors = payload.get("selectors", [])
            return {"selectors": selectors[:max_results], "count": min(len(selectors), max_results)}
        payload = self._request_json(
            "POST",
            "/phonebook/search",
            {
                "term": term,
                "maxresults": min(max_results, self.config.max_results_per_search),
                "target": target,
            },
            extra_headers={"content-type": "text/plain"},
        )
        selectors = payload.get("selectors", [])
        return {"selectors": selectors, "count": len(selectors)}

    def search_saudi_infrastructure(self) -> dict[str, Any]:
        terms: dict[str, Any] = {}
        for term in self.config.saudi_search_terms:
            result = self.search(term=term, max_results=50)
            records = result.get("records", [])
            buckets: dict[str, int] = {}
            latest = ""
            for record in records:
                bucket = str(record.get("bucket", "unknown"))
                buckets[bucket] = buckets.get(bucket, 0) + 1
                date_value = str(record.get("date", ""))
                if date_value > latest:
                    latest = date_value
            terms[term] = {"count": len(records), "buckets": buckets, "latest": latest}
        return {"terms": terms}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        action = params.get("action", "search")
        if action == "phonebook":
            return self.search_phonebook(
                term=str(params.get("term", "aramco.com")),
                target=int(params.get("target", 1)),
                max_results=int(params.get("max_results", 100)),
            )
        if action == "saudi":
            return self.search_saudi_infrastructure()
        return self.search(
            term=str(params.get("term", "aramco.com")),
            max_results=int(params.get("max_results", 50)),
            media=int(params.get("media", 0)),
            sort=int(params.get("sort", 4)),
        )

    def _poll_search_results(self, search_id: str, limit: int = 50) -> dict[str, Any]:
        if self.is_airgapped:
            pending = self._read_json(self.fixture_dir / "search_status_pending.json")
            complete = self._read_json(self.fixture_dir / "search_status_complete.json")
            for payload in [pending, complete]:
                if int(payload.get("status", 0)) == 2:
                    records = payload.get("records", [])
                    return {
                        "records": records[:limit],
                        "count": min(len(records), limit),
                        "search_id": search_id,
                        "status": 2,
                    }
            return {"records": [], "count": 0, "search_id": search_id, "status": 0}

        for _ in range(self.config.max_poll_attempts):
            polled = self._request_json("GET", f"/intelligent/search/result?id={parse.quote(search_id)}&limit={limit}")
            status = int(polled.get("status", 0))
            if status == 2:
                records = polled.get("records", [])
                return {"records": records, "count": len(records), "search_id": search_id, "status": status}
            time.sleep(self.config.poll_interval_seconds)
        return {"records": [], "count": 0, "search_id": search_id, "status": 0}

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "records" in raw_data:
            return [self.normalizer.normalize_record(record) for record in raw_data.get("records", [])]
        if "selectors" in raw_data:
            return self.normalizer.normalize_phonebook(raw_data.get("selectors", []))
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
        return {
            "status": "ok" if bool(self._api_key()) else "degraded",
            "latency_ms": 100.0,
            "last_successful_fetch": datetime.now(timezone.utc),
            "error_count": 0,
            "detail": "online auth key validation",
        }
