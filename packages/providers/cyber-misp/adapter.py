"""MISP bulk threat-intel ingestion adapter (not IR workflow adapter)."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import MISPConfig
from .normalizer import MISPNormalizer


class MISPThreatIntelAdapter(ProviderAdapter):
    def __init__(self, config: MISPConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or MISPConfig()
        self.normalizer = MISPNormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="cyber-misp",
            category=ProviderCategory.CYBER_THREAT_INTEL,
            tier=ProviderTier.FREE,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["MISP_URL", "MISP_API_KEY"],
            supported_schemas=["NormalizedThreatIndicator"],
        )

    def _headers(self) -> dict[str, str]:
        api_key = os.getenv("S3M_MISP_API_KEY") or os.getenv("MISP_API_KEY") or ""
        return {"Authorization": api_key, "Accept": "application/json"}

    def _base_url(self) -> str:
        return (os.getenv("S3M_MISP_URL") or os.getenv("MISP_URL") or self.config.base_url).rstrip("/")

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"valid": (self._fixture_dir() / "fixtures" / "attributes_response.json").exists(), "mode": "airgapped"}
        response = self._request("GET", f"{self._base_url()}/servers/getVersion", headers=self._headers(), verify_ssl=self.config.verify_ssl)
        return {"valid": "error" not in response, "detail": response}

    def fetch_indicators(self, days_back: int = 7, types: list[str] | None = None, limit: int = 500) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("attributes_response.json")
            attrs = payload.get("Attribute", [])
            return {"attributes": attrs[:limit], "count": min(limit, len(attrs))}
        body = {
            "type": types or self.config.relevant_attribute_types,
            "last": f"{int(days_back)}d",
            "enforceWarninglist": self.config.enforce_warninglist,
            "limit": int(limit),
        }
        data = self._request("POST", f"{self._base_url()}/attributes/restSearch", headers=self._headers(), payload=body, verify_ssl=self.config.verify_ssl)
        attrs = data.get("Attribute", []) if isinstance(data, dict) else []
        return {"attributes": attrs, "count": len(attrs), "raw": data}

    def fetch_events(self, days_back: int = 30, limit: int = 50) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("events_response.json")
            events = payload.get("Event", [])
            return {"events": events[:limit], "count": min(limit, len(events))}
        body = {"last": f"{int(days_back)}d", "published": True, "limit": int(limit), "includeAttachments": False}
        data = self._request("POST", f"{self._base_url()}/events/restSearch", headers=self._headers(), payload=body, verify_ssl=self.config.verify_ssl)
        events = data.get("Event", []) if isinstance(data, dict) else []
        return {"events": events, "count": len(events), "raw": data}

    def fetch_galaxies(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("galaxies_response.json")
            galaxies = payload.get("Galaxy", [])
            return {"galaxies": galaxies, "count": len(galaxies)}
        data = self._request("GET", f"{self._base_url()}/galaxies", headers=self._headers(), verify_ssl=self.config.verify_ssl)
        galaxies = data.get("response", data.get("Galaxy", [])) if isinstance(data, dict) else []
        if not isinstance(galaxies, list):
            galaxies = []
        return {"galaxies": galaxies, "count": len(galaxies), "raw": data}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        endpoint = params.get("endpoint", "attributes")
        if endpoint == "attributes":
            last = params.get("last")
            days_back = int(str(last).rstrip("d")) if isinstance(last, str) and last.endswith("d") else int(params.get("days_back", self.config.default_last_days))
            return self.fetch_indicators(days_back=days_back, types=params.get("types"), limit=int(params.get("limit", self.config.default_limit)))
        if endpoint == "events":
            last = params.get("last")
            days_back = int(str(last).rstrip("d")) if isinstance(last, str) and last.endswith("d") else int(params.get("days_back", 30))
            return self.fetch_events(days_back=days_back, limit=int(params.get("limit", 50)))
        if endpoint == "galaxies":
            return self.fetch_galaxies()
        return self.fetch_indicators()

    def normalize(self, raw_data: dict[str, Any]) -> list:
        attributes = raw_data.get("attributes") or raw_data.get("Attribute") or []
        event_map = {str(e.get("id", "")): e for e in raw_data.get("events", [])}
        return self.normalizer.normalize_batch(attributes, event_map=event_map)

    def health_check(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            fixture = self._fixture_dir() / "fixtures" / "attributes_response.json"
            age = None
            if fixture.exists():
                age = max(0.0, (datetime.now(tz=UTC) - datetime.fromtimestamp(fixture.stat().st_mtime, tz=UTC)).total_seconds())
            return {"status": "ok" if fixture.exists() else "error", "detail": {"mode": "airgapped", "fixture_age_seconds": age}}
        version = self._request("GET", f"{self._base_url()}/servers/getVersion", headers=self._headers(), verify_ssl=self.config.verify_ssl)
        stats = self._request("GET", f"{self._base_url()}/attributes/attributeStatistics/type/percentage", headers=self._headers(), verify_ssl=self.config.verify_ssl)
        return {"status": "ok" if "error" not in version and "error" not in stats else "error", "detail": {"version": version, "attribute_stats": stats}}
