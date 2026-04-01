"""GreyNoise adapter used to reduce false positives in SOC triage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import GreyNoiseConfig
from .normalizer import GreyNoiseNormalizer


class GreyNoiseAdapter(ProviderAdapter):
    def __init__(self, config: GreyNoiseConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or GreyNoiseConfig()
        self.normalizer = GreyNoiseNormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="cyber-greynoise",
            category=ProviderCategory.CYBER_THREAT_INTEL,
            tier=ProviderTier.FREEMIUM,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["GREYNOISE_API_KEY"],
            supported_schemas=["NormalizedThreatIndicator"],
        )

    def check_ip(self, ip: str) -> dict[str, Any]:
        if self.mode == "airgapped":
            mapping = {
                "198.51.100.1": "ip_noise_malicious.json",
                "198.51.100.2": "ip_noise_benign.json",
                "8.8.8.8": "ip_riot.json",
            }
            filename = mapping.get(ip, "ip_targeted.json")
            payload = self._load_fixture_json(filename)
            payload["ip"] = ip
            return payload
        return self._request("GET", f"{self.config.base_url}{self.config.community_endpoint}/{ip}")

    def check_batch(self, ips: list[str]) -> list[dict[str, Any]]:
        return [self.check_ip(ip) for ip in ips]

    def is_noise(self, ip: str) -> bool:
        return bool(self.check_ip(ip).get("noise", False))

    def is_riot(self, ip: str) -> bool:
        return bool(self.check_ip(ip).get("riot", False))

    def fetch(self, params: dict[str, Any]):
        if "ips" in params:
            return self.check_batch(list(params.get("ips", [])))
        return self.check_ip(str(params.get("value", params.get("ip", ""))))

    def normalize(self, raw_data: dict[str, Any]):
        return self.normalizer.normalize_ip(raw_data)

    def health_check(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"status": "ok", "detail": {"mode": "airgapped"}}
        out = self.check_ip("8.8.8.8")
        return {"status": "ok" if "error" not in out else "error", "detail": out}
