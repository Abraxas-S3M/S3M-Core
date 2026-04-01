"""AbuseIPDB adapter for fast IP reputation enrichment."""

from __future__ import annotations

from pathlib import Path
import urllib.parse
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import AbuseIPDBConfig
from .normalizer import AbuseIPDBNormalizer


class AbuseIPDBAdapter(ProviderAdapter):
    def __init__(self, config: AbuseIPDBConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or AbuseIPDBConfig()
        self.normalizer = AbuseIPDBNormalizer(self.config)

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="cyber-abuseipdb",
            category=ProviderCategory.CYBER_THREAT_INTEL,
            tier=ProviderTier.FREEMIUM,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["ABUSEIPDB_API_KEY"],
            supported_schemas=["NormalizedThreatIndicator"],
        )

    def check_ip(self, ip: str, max_age_days: int = 90) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("ip_check_malicious.json")
            payload["query"] = {"type": "ip", "value": ip}
            return payload
        q = urllib.parse.urlencode({"ipAddress": ip, "maxAgeInDays": int(max_age_days), "verbose": ""})
        return self._request("GET", f"{self.config.base_url}/check?{q}")

    def check_cidr(self, cidr: str, max_age_days: int = 30) -> dict[str, Any]:
        if self.mode == "airgapped":
            return self._load_fixture_json("blacklist_response.json")
        q = urllib.parse.urlencode({"network": cidr, "maxAgeInDays": int(max_age_days)})
        return self._request("GET", f"{self.config.base_url}/check-block?{q}")

    def get_blacklist(self, confidence_min: int = 90, limit: int = 1000) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("blacklist_response.json")
            payload["data"] = payload.get("data", [])[:limit]
            return payload
        q = urllib.parse.urlencode({"confidenceMinimum": int(confidence_min), "limit": int(limit)})
        return self._request("GET", f"{self.config.base_url}/blacklist?{q}")

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        t = str(params.get("type", "ip")).lower()
        if t == "ip":
            return self.check_ip(str(params.get("value", "")), max_age_days=int(params.get("max_age_days", self.config.default_max_age_days)))
        if t == "cidr":
            return self.check_cidr(str(params.get("value", "")), max_age_days=int(params.get("max_age_days", 30)))
        if t == "blacklist":
            return self.get_blacklist(confidence_min=int(params.get("confidence_min", 90)), limit=int(params.get("limit", 1000)))
        return {"error": "unsupported_type", "detail": t}

    def normalize(self, raw_data: dict[str, Any]):
        if isinstance(raw_data.get("data"), list):
            return self.normalizer.normalize_blacklist(raw_data.get("data", []))
        return self.normalizer.normalize_ip_check(raw_data.get("data", raw_data))

    def health_check(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"status": "ok", "detail": {"mode": "airgapped"}}
        out = self.check_ip("8.8.8.8")
        return {"status": "ok" if "error" not in out else "error", "detail": out}
