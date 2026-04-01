"""Shared provider abstractions for CTI integration adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import ssl
import urllib.error
import urllib.request
from typing import Any


class ProviderCategory(str, Enum):
    CYBER_THREAT_INTEL = "CYBER_THREAT_INTEL"
    GEOINT = "GEOINT"
    SOVEREIGN_REGIONAL = "SOVEREIGN_REGIONAL"


class ProviderTier(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    GOVERNMENT = "GOVERNMENT"


@dataclass
class ProviderManifest:
    provider_id: str
    category: ProviderCategory
    tier: ProviderTier
    auth_type: str
    rate_limit_rpm: int
    name: str = ""
    base_url: str = ""
    required_env_vars: list[str] = field(default_factory=list)
    optional_env_vars: list[str] = field(default_factory=list)
    supported_schemas: list[str] = field(default_factory=lambda: ["NormalizedThreatIndicator"])
    description: str = ""
    docs_url: str = ""
    airgap_capable: bool = True
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


class ProviderAdapter:
    """Base adapter with secure request handling and fixture support."""

    def __init__(self, mode: str = "airgapped") -> None:
        self.mode = (mode or "airgapped").strip().lower()

    def _load_fixture_json(self, filename: str) -> dict[str, Any]:
        fixture = self._fixture_dir() / "fixtures" / filename
        with fixture.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        verify_ssl: bool = True,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        data: bytes | None = None
        req_headers = headers.copy() if headers else {}
        if payload is not None:
            req_headers.setdefault("Content-Type", "application/json")
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url=url, method=method.upper(), headers=req_headers, data=data)

        context = None
        if not verify_ssl:
            context = ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8") if exc.fp else ""
            return {"error": f"http_{exc.code}", "detail": detail}
        except Exception as exc:  # pragma: no cover
            return {"error": "request_failed", "detail": str(exc)}
