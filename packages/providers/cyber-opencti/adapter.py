"""OpenCTI GraphQL ingestion adapter for structured CTI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import OpenCTIConfig
from .normalizer import OpenCTINormalizer


class OpenCTIAdapter(ProviderAdapter):
    def __init__(self, config: OpenCTIConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or OpenCTIConfig()
        self.normalizer = OpenCTINormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _base_url(self) -> str:
        return (os.getenv("S3M_OPENCTI_URL") or os.getenv("OPENCTI_URL") or self.config.base_url).rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = os.getenv("S3M_OPENCTI_TOKEN") or os.getenv("OPENCTI_TOKEN") or ""
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="cyber-opencti",
            category=ProviderCategory.CYBER_THREAT_INTEL,
            tier=ProviderTier.FREE,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["OPENCTI_URL", "OPENCTI_TOKEN"],
            supported_schemas=["NormalizedThreatIndicator"],
        )

    def _graphql(self, query: str) -> dict[str, Any]:
        return self._request("POST", f"{self._base_url()}{self.config.graphql_endpoint}", headers=self._headers(), payload={"query": query}, verify_ssl=True)

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"valid": (self._fixture_dir() / "fixtures" / "indicators_response.json").exists(), "mode": "airgapped"}
        res = self._graphql("{ __typename }")
        return {"valid": "error" not in res, "detail": res}

    def fetch_indicators(self, days_back: int = 30, limit: int = 100) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("indicators_response.json")
            nodes = [edge.get("node", {}) for edge in payload.get("data", {}).get("indicators", {}).get("edges", [])]
            return {"indicators": nodes[:limit], "count": min(limit, len(nodes))}
        q = f"""{{ indicators(first: {int(limit)}) {{ edges {{ node {{ id name pattern pattern_type valid_from valid_until x_opencti_score created_at objectLabel {{ value }} killChainPhases {{ kill_chain_name phase_name }} createdBy {{ name }} }} }} }} }}"""
        data = self._graphql(q)
        nodes = [edge.get("node", {}) for edge in data.get("data", {}).get("indicators", {}).get("edges", [])]
        return {"indicators": nodes, "count": len(nodes), "raw": data}

    def fetch_threat_actors(self, limit: int = 50) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("threat_actors_response.json")
            nodes = [edge.get("node", {}) for edge in payload.get("data", {}).get("threatActors", {}).get("edges", [])]
            return {"threat_actors": nodes[:limit], "count": min(limit, len(nodes))}
        q = f"""{{ threatActors(first: {int(limit)}) {{ edges {{ node {{ id name description aliases first_seen last_seen sophistication resource_level primary_motivation objectLabel {{ value }} }} }} }} }}"""
        data = self._graphql(q)
        nodes = [edge.get("node", {}) for edge in data.get("data", {}).get("threatActors", {}).get("edges", [])]
        return {"threat_actors": nodes, "count": len(nodes), "raw": data}

    def fetch_malware(self, limit: int = 50) -> dict[str, Any]:
        if self.mode == "airgapped":
            payload = self._load_fixture_json("malware_response.json")
            nodes = [edge.get("node", {}) for edge in payload.get("data", {}).get("malwares", {}).get("edges", [])]
            return {"malware": nodes[:limit], "count": min(limit, len(nodes))}
        q = f"""{{ malwares(first: {int(limit)}) {{ edges {{ node {{ id name description is_family malware_types first_seen last_seen objectLabel {{ value }} killChainPhases {{ phase_name }} }} }} }} }}"""
        data = self._graphql(q)
        nodes = [edge.get("node", {}) for edge in data.get("data", {}).get("malwares", {}).get("edges", [])]
        return {"malware": nodes, "count": len(nodes), "raw": data}

    def fetch_reports(self, limit: int = 20) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"reports": [], "count": 0}
        q = f"""{{ reports(first: {int(limit)}, orderBy: published, orderMode: desc) {{ edges {{ node {{ id name description published confidence objectLabel {{ value }} }} }} }} }}"""
        data = self._graphql(q)
        nodes = [edge.get("node", {}) for edge in data.get("data", {}).get("reports", {}).get("edges", [])]
        return {"reports": nodes, "count": len(nodes), "raw": data}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        endpoint = params.get("endpoint", "indicators")
        if endpoint == "indicators":
            return self.fetch_indicators(days_back=int(params.get("days_back", 30)), limit=int(params.get("limit", self.config.default_limit)))
        if endpoint == "threat_actors":
            return self.fetch_threat_actors(limit=int(params.get("limit", 50)))
        if endpoint == "malware":
            return self.fetch_malware(limit=int(params.get("limit", 50)))
        if endpoint == "reports":
            return self.fetch_reports(limit=int(params.get("limit", 20)))
        return self.fetch_indicators()

    def normalize(self, raw_data: dict[str, Any]) -> list:
        return self.normalizer.normalize_batch(raw_data.get("indicators", []))

    def health_check(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"status": "ok", "detail": {"mode": "airgapped", "ping": "fixture"}}
        res = self._graphql("{ __typename }")
        return {"status": "ok" if "error" not in res else "error", "detail": res}
