"""Compatibility layer for integration SDK provider interfaces.

Tactical context:
- Preserves provider behavior in sovereign/offline deployments when the
  shared integration framework package is unavailable in a minimal runtime.
"""

from __future__ import annotations

import importlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Type
from urllib import error, parse, request


def _load_framework_symbol(symbol_name: str) -> Any:
    """Try known integration SDK module paths, return symbol if found."""
    candidate_modules = [
        "packages.integration_sdk",
        "packages.integration_sdk.provider",
        "packages.integration_sdk.providers",
        "packages.integration_sdk.registry",
        "packages.integration_sdk.models",
    ]
    for module_name in candidate_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, symbol_name):
            return getattr(module, symbol_name)
    return None


_ProviderCategory = _load_framework_symbol("ProviderCategory")
_ProviderTier = _load_framework_symbol("ProviderTier")
_ProviderManifest = _load_framework_symbol("ProviderManifest")
_ProviderAdapter = _load_framework_symbol("ProviderAdapter")
_ProviderRegistry = _load_framework_symbol("ProviderRegistry")
_SecretProvider = _load_framework_symbol("SecretProvider")
_ResilientClient = _load_framework_symbol("ResilientClient")


class ProviderCategory(str, Enum):
    GEOINT = "GEOINT"


class ProviderTier(str, Enum):
    FREE = "FREE"


@dataclass
class ProviderManifest:
    provider_id: str
    name: str
    category: ProviderCategory
    tier: ProviderTier
    base_url: str
    auth_type: str
    rate_limit_rpm: int
    supported_schemas: list[str]
    required_env_vars: list[str]
    description: str
    docs_url: str
    airgap_capable: bool
    enabled: bool
    tags: list[str] = field(default_factory=list)


class ProviderAdapter:
    """Base adapter interface used by provider implementations."""

    def get_manifest(self) -> ProviderManifest:
        raise NotImplementedError


class ProviderRegistry:
    """Simple in-process provider registry."""

    _providers: Dict[str, Type[ProviderAdapter]] = {}

    @classmethod
    def register(cls, adapter_cls: Type[ProviderAdapter]) -> None:
        manifest = adapter_cls().get_manifest()
        cls._providers[manifest.provider_id] = adapter_cls

    @classmethod
    def get_adapter(cls, provider_id: str) -> Optional[ProviderAdapter]:
        adapter_cls = cls._providers.get(provider_id)
        if adapter_cls is None:
            return None
        return adapter_cls()

    @classmethod
    def list_provider_ids(cls) -> list[str]:
        return sorted(cls._providers.keys())


class SecretProvider:
    """Env-backed secret provider with S3M prefix fallback."""

    @staticmethod
    def get_secret(key: str) -> Optional[str]:
        direct = os.getenv(key)
        if direct:
            return direct
        if key.startswith("S3M_"):
            return None
        return os.getenv(f"S3M_{key}")


class ResilientClient:
    """Small retrying HTTP client for constrained/offline-aware environments."""

    def __init__(self, timeout_seconds: int = 60, retries: int = 3, backoff_s: float = 0.4):
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_s = backoff_s

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        body = self._request("GET", url, headers=headers)
        return json.loads(body.decode("utf-8"))

    def post_form_json(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        payload = parse.urlencode(data).encode("utf-8")
        merged_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            merged_headers.update(headers)
        body = self._request("POST", url, data=payload, headers=merged_headers)
        return json.loads(body.decode("utf-8"))

    def _request(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries):
            req = request.Request(url=url, data=data, method=method, headers=headers or {})
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return resp.read()
            except (error.URLError, error.HTTPError, TimeoutError, ValueError) as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("HTTP request failed without exception")


if _ProviderCategory is not None:
    ProviderCategory = _ProviderCategory
if _ProviderTier is not None:
    ProviderTier = _ProviderTier
if _ProviderManifest is not None:
    ProviderManifest = _ProviderManifest
if _ProviderAdapter is not None:
    ProviderAdapter = _ProviderAdapter
if _ProviderRegistry is not None:
    ProviderRegistry = _ProviderRegistry
if _SecretProvider is not None:
    SecretProvider = _SecretProvider
if _ResilientClient is not None:
    ResilientClient = _ResilientClient
