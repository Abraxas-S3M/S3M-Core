"""Read-only adapter for allowlisted external World Monitor fallback.

Military/tactical context:
This adapter provides controlled contingency intelligence views when the local
runtime is unavailable, while preventing uncontrolled external data ingestion.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlencode, urlparse

import requests


ALLOWED_HOSTS = {"www.worldmonitor.app", "api.worldmonitor.app"}


class BoundedTTLCache:
    """Small bounded cache for short-lived fallback payloads."""

    def __init__(self, max_entries: int = 32, ttl_seconds: int = 30) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._items: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            expires_at = time.monotonic() + self.ttl_seconds
            self._items[key] = (expires_at, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


class SlidingWindowRateLimiter:
    """Bounded in-memory request throttle to protect upstreams."""

    def __init__(self, per_minute: int = 30, max_keys: int = 128) -> None:
        self.per_minute = per_minute
        self.max_keys = max_keys
        self._hits: "OrderedDict[str, deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - 60.0
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_keys:
                    self._hits.popitem(last=False)
                hits = deque()
                self._hits[key] = hits
            while hits and hits[0] < window_start:
                hits.popleft()
            if len(hits) >= self.per_minute:
                retry_after = max(1, int(60 - (now - hits[0])))
                return False, retry_after
            hits.append(now)
            self._hits.move_to_end(key)
            return True, 0


@dataclass
class ProxyResult:
    status_code: int
    content: bytes
    content_type: str
    upstream_url: str


class ExternalWorldMonitorAdapter:
    """Allowlisted external fallback adapter with bounded-memory safety."""

    def __init__(
        self,
        timeout_seconds: float = 4.0,
        max_response_bytes: int = 10 * 1024 * 1024,
        cache_ttl_seconds: int = 30,
        cache_max_entries: int = 32,
        requests_per_minute: int = 30,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.cache = BoundedTTLCache(max_entries=cache_max_entries, ttl_seconds=cache_ttl_seconds)
        self.rate_limiter = SlidingWindowRateLimiter(per_minute=requests_per_minute)

    def fallback_health(self, client_key: str = "global") -> dict[str, Any]:
        cached = self.cache.get("fallback-health")
        if cached is not None:
            return cached
        rate = self._check_rate("fallback-health", client_key)
        if rate is not None:
            return rate

        candidates = [
            "https://api.worldmonitor.app/health",
            "https://api.worldmonitor.app/status",
            "https://www.worldmonitor.app/",
        ]
        errors: list[str] = []
        for url in candidates:
            try:
                status_code, _, _, _ = self._fetch(url, is_api="api.worldmonitor.app" in url)
                payload = {
                    "available": status_code < 500,
                    "status": "ok" if status_code < 500 else "degraded",
                    "upstream_url": url,
                    "upstream_status": status_code,
                }
                self.cache.set("fallback-health", payload)
                return payload
            except Exception as exc:  # pragma: no cover - defensive branch
                errors.append(str(exc))
        payload = {"available": False, "status": "down", "detail": "; ".join(errors[:2])}
        self.cache.set("fallback-health", payload)
        return payload

    def fallback_bootstrap(self, client_key: str = "global") -> tuple[int, dict[str, Any]]:
        cache_key = "fallback-bootstrap"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return 200, cached
        rate = self._check_rate("fallback-bootstrap", client_key)
        if rate is not None:
            return 429, rate
        try:
            status_code, headers, body, upstream_url = self._fetch("https://www.worldmonitor.app/", is_api=False)
            payload = self._payload_from_response(status_code, headers, body, upstream_url)
            if status_code < 400:
                self.cache.set(cache_key, payload)
            return (200 if status_code < 400 else 503), payload
        except Exception as exc:
            return 503, {"status": "unavailable", "detail": str(exc)}

    def fallback_feed(self, client_key: str = "global") -> tuple[int, dict[str, Any]]:
        cache_key = "fallback-feed"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return 200, cached
        rate = self._check_rate("fallback-feed", client_key)
        if rate is not None:
            return 429, rate
        candidates = [
            "https://api.worldmonitor.app/feed",
            "https://api.worldmonitor.app/api/feed",
            "https://api.worldmonitor.app/v1/feed",
        ]
        for url in candidates:
            try:
                status_code, headers, body, upstream_url = self._fetch(url, is_api=True)
                payload = self._payload_from_response(status_code, headers, body, upstream_url)
                if status_code < 400:
                    self.cache.set(cache_key, payload)
                    return 200, payload
            except Exception:
                continue
        return 503, {"status": "unavailable", "detail": "live feed endpoint unavailable"}

    def proxy_runtime(
        self,
        path: str,
        query_params: dict[str, Any] | None = None,
        client_key: str = "global",
    ) -> ProxyResult | dict[str, Any]:
        safe_path = self._normalize_path(path)
        if safe_path.startswith("api/"):
            base = "https://api.worldmonitor.app"
            rel_path = safe_path[len("api/") :]
            is_api = True
        else:
            base = "https://www.worldmonitor.app"
            rel_path = safe_path
            is_api = False
        url = f"{base}/{rel_path}".rstrip("/")
        if not rel_path:
            url = f"{base}/"

        query = query_params or {}
        cache_key = f"runtime:{url}?{urlencode(sorted((str(k), str(v)) for k, v in query.items()))}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return ProxyResult(
                status_code=int(cached["status_code"]),
                content=cached["content"],
                content_type=str(cached["content_type"]),
                upstream_url=str(cached["upstream_url"]),
            )
        rate = self._check_rate("runtime-proxy", client_key)
        if rate is not None:
            return rate
        status_code, headers, body, upstream_url = self._fetch(url, params=query, is_api=is_api)
        content_type = headers.get("content-type", "application/octet-stream")
        if status_code < 400:
            self.cache.set(
                cache_key,
                {
                    "status_code": status_code,
                    "content_type": content_type,
                    "content": body,
                    "upstream_url": upstream_url,
                },
            )
        return ProxyResult(
            status_code=status_code,
            content=body,
            content_type=content_type,
            upstream_url=upstream_url,
        )

    def _check_rate(self, operation: str, client_key: str) -> dict[str, Any] | None:
        allowed, retry_after = self.rate_limiter.allow(f"{operation}:{client_key}")
        if allowed:
            return None
        return {
            "status": "rate_limited",
            "detail": "fallback request rate limit exceeded",
            "retry_after_seconds": retry_after,
        }

    def _normalize_path(self, path: str) -> str:
        raw = (path or "").strip()
        decoded = unquote(raw)
        if "://" in decoded or decoded.startswith("//") or "\\" in decoded:
            raise ValueError("absolute URLs are not allowed")
        safe_path = decoded.lstrip("/")
        if any(segment == ".." for segment in safe_path.split("/")):
            raise ValueError("path traversal is not allowed")
        return safe_path

    def _build_headers(self, is_api: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Encoding": "identity",
            "User-Agent": "S3M-WorldIntelligenceGateway/1.0",
        }
        if is_api:
            api_key = os.getenv("WORLDMONITOR_API_KEY", "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                headers["x-api-key"] = api_key
        return headers

    def _fetch(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        is_api: bool = False,
    ) -> tuple[int, dict[str, str], bytes, str]:
        self._enforce_allowlist(url)
        response = requests.get(
            url,
            params=params or {},
            headers=self._build_headers(is_api=is_api),
            timeout=self.timeout_seconds,
            stream=True,
        )
        body = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > self.max_response_bytes:
                raise ValueError("upstream response exceeded size limit")
        headers = {k.lower(): v for k, v in response.headers.items()}
        return response.status_code, headers, bytes(body), str(response.url)

    def _enforce_allowlist(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in ALLOWED_HOSTS:
            raise ValueError("external URL not allowlisted")

    def _payload_from_response(
        self,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
        upstream_url: str,
    ) -> dict[str, Any]:
        content_type = headers.get("content-type", "")
        payload: dict[str, Any] = {
            "status": "ok" if status_code < 400 else "error",
            "upstream_url": upstream_url,
            "upstream_status": status_code,
            "content_type": content_type,
        }
        if "application/json" in content_type:
            try:
                payload["data"] = response_json = json.loads(body.decode("utf-8"))
                if isinstance(response_json, list) and len(response_json) > 50:
                    payload["data"] = response_json[:50]
            except Exception:
                payload["data"] = {"raw_preview": body.decode("utf-8", errors="replace")[:4000]}
        else:
            payload["data"] = {"raw_preview": body.decode("utf-8", errors="replace")[:4000]}
        return payload
