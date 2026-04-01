"""VirusTotal adapter for IOC reputation enrichment."""

from __future__ import annotations

import base64
from pathlib import Path
import time
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import VirusTotalConfig
from .normalizer import VirusTotalNormalizer


class VirusTotalAdapter(ProviderAdapter):
    def __init__(self, config: VirusTotalConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or VirusTotalConfig()
        self.normalizer = VirusTotalNormalizer(malicious_threshold=self.config.malicious_threshold)

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="cyber-virustotal",
            category=ProviderCategory.CYBER_THREAT_INTEL,
            tier=ProviderTier.FREEMIUM,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["VIRUSTOTAL_API_KEY"],
            supported_schemas=["NormalizedThreatIndicator"],
        )

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"valid": True, "mode": "airgapped"}
        out = self.lookup_ip("8.8.8.8")
        return {"valid": "error" not in out, "detail": out}

    def lookup_ip(self, ip: str) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("ip_report_malicious.json")
            payload["query"] = {"type": "ip", "value": ip}
            return payload
        return self._request("GET", f"{self.config.base_url}/ip_addresses/{ip}")

    def lookup_domain(self, domain: str) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("domain_report_phishing.json")
            payload["query"] = {"type": "domain", "value": domain}
            return payload
        return self._request("GET", f"{self.config.base_url}/domains/{domain}")

    def lookup_hash(self, hash_value: str) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("hash_report_malware.json")
            payload["query"] = {"type": "hash", "value": hash_value}
            return payload
        return self._request("GET", f"{self.config.base_url}/files/{hash_value}")

    def lookup_url(self, url: str) -> dict[str, Any]:
        encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
        if self.mode == "airgapped":
            payload = self._load_fixture_json("domain_report_phishing.json")
            payload["query"] = {"type": "url", "value": url, "encoded": encoded}
            return payload
        return self._request("GET", f"{self.config.base_url}/urls/{encoded}")

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        t = str(params.get("type", "ip")).lower()
        v = str(params.get("value", ""))
        if t == "ip":
            return self.lookup_ip(v)
        if t == "domain":
            return self.lookup_domain(v)
        if t == "hash":
            return self.lookup_hash(v)
        if t == "url":
            return self.lookup_url(v)
        return {"error": "unsupported_type", "detail": t}

    def normalize(self, raw_data: dict[str, Any]):
        t = str(raw_data.get("query", {}).get("type") or raw_data.get("data", {}).get("type") or "ip").lower()
        if t in {"ip", "ip_address"}:
            return self.normalizer.normalize_ip_report(raw_data)
        if t == "domain":
            return self.normalizer.normalize_domain_report(raw_data)
        if t in {"hash", "file"}:
            return self.normalizer.normalize_hash_report(raw_data)
        if t == "url":
            return self.normalizer.normalize_domain_report(raw_data)
        return self.normalizer.normalize_ip_report(raw_data)

    def health_check(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"status": "ok", "detail": {"mode": "airgapped", "latency_ms": 0.0}}
        start = time.perf_counter()
        _ = self.lookup_ip("8.8.8.8")
        return {"status": "ok", "detail": {"latency_ms": round((time.perf_counter()-start)*1000.0, 2)}}
