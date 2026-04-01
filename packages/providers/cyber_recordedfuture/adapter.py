"""Recorded Future adapter with fixture-based premium threat intelligence."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import RecordedFutureConfig
from .normalizer import RecordedFutureNormalizer


class RecordedFutureAdapter(ProviderAdapter):
    provider_id = "cyber-recordedfuture"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = RecordedFutureConfig()
        self.normalizer = RecordedFutureNormalizer(self.config)
        self.fixture_dir = Path(__file__).resolve().parents[1] / "cyber-recordedfuture" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="CYBER_THREAT_INTEL",
            tier="PREMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["RECORDED_FUTURE_API_KEY"],
            description="Recorded Future predictive threat intelligence for IOC prioritization.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "ip_high_risk.json").exists()
        return bool(self._env("RECORDED_FUTURE_API_KEY"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def lookup_ip(self, ip: str) -> dict[str, Any]:
        payload = self._load_fixture("ip_high_risk.json") if self.is_airgapped else {}
        payload["value"] = ip
        payload["entity_type"] = "ip"
        return payload

    def lookup_domain(self, domain: str) -> dict[str, Any]:
        payload = self._load_fixture("domain_low_risk.json") if self.is_airgapped else {}
        payload["value"] = domain
        payload["entity_type"] = "domain"
        return payload

    def lookup_hash(self, hash_value: str) -> dict[str, Any]:
        payload = self._load_fixture("ip_high_risk.json") if self.is_airgapped else {}
        payload["value"] = hash_value
        payload["entity_type"] = "hash"
        return payload

    def lookup_cve(self, cve: str) -> dict[str, Any]:
        payload = self._load_fixture("cve_critical.json") if self.is_airgapped else {}
        payload["value"] = cve
        payload["entity_type"] = "vulnerability"
        return payload

    def search_threat_actors(self, query: str) -> dict[str, Any]:
        payload = self._load_fixture("threat_actor.json") if self.is_airgapped else {}
        payload["query"] = query
        return payload

    def get_alerts(self, limit: int = 20) -> dict[str, Any]:
        alert = self._load_fixture("cve_critical.json") if self.is_airgapped else {}
        return {"alerts": [alert for _ in range(max(1, min(limit, 3)))], "count": max(1, min(limit, 3))}

    def get_risk_list(self, entity_type: str = "ip", min_risk: int = 65, limit: int = 100) -> dict[str, Any]:
        candidates = [self._load_fixture("ip_high_risk.json"), self._load_fixture("domain_low_risk.json"), self._load_fixture("cve_critical.json")]
        out = []
        for item in candidates:
            score = int(item.get("risk_score", 0))
            if score >= min_risk:
                clone = dict(item)
                clone["entity_type"] = entity_type if entity_type != "any" else clone.get("entity_type", "ip")
                out.append(clone)
        return {"entities": out[:limit], "count": len(out[:limit])}

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "ip"))
        if endpoint == "domain":
            return self.lookup_domain(str(params.get("value", "example.com")))
        if endpoint == "hash":
            return self.lookup_hash(str(params.get("value", "0" * 64)))
        if endpoint == "cve":
            return self.lookup_cve(str(params.get("value", "CVE-2024-0001")))
        if endpoint == "threat_actor":
            return self.search_threat_actors(str(params.get("query", "APT")))
        if endpoint == "alerts":
            return self.get_alerts(int(params.get("limit", 20)))
        if endpoint == "risk_list":
            return self.get_risk_list(str(params.get("entity_type", "ip")), int(params.get("min_risk", 65)), int(params.get("limit", 100)))
        return self.lookup_ip(str(params.get("value", "203.0.113.5")))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "risk_score" in raw_data and "entity_type" in raw_data:
            return self.normalizer.normalize_entity(raw_data)
        if isinstance(raw_data, dict) and "name" in raw_data and "ttps" in raw_data:
            return self.normalizer.normalize_threat_actor(raw_data)
        if isinstance(raw_data, dict) and "entities" in raw_data:
            indicators = [self.normalizer.normalize_entity(item) for item in raw_data.get("entities", [])]
            return {"indicators": indicators, "count": len(indicators)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture IOC intelligence available" if self.is_airgapped else "api key check",
        }
