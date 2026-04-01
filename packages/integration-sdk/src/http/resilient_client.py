"""Resilient HTTP client with retries, backoff, and safety controls."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from base.provider_adapter import OperatingMode
from errors.integration_errors import AirgapViolationError, CircuitBreakerOpenError, ProviderFetchError
from .circuit_breaker import CircuitBreaker
from .rate_limiter import RateLimiter


class _FallbackLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        return

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return

    def error(self, *args: Any, **kwargs: Any) -> None:
        return


class ResilientHTTPClient:
    """Provider HTTP client with tactical resilience and air-gap enforcement."""

    def __init__(
        self,
        provider_id: str,
        mode: OperatingMode = OperatingMode.ONLINE,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self.provider_id = provider_id
        self.mode = mode
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.logger = logger or _FallbackLogger()

    @staticmethod
    def _sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
        out = {}
        for key, value in headers.items():
            lowered = key.lower()
            if any(token in lowered for token in ("authorization", "x-api-key", "token", "secret", "password")):
                out[key] = "***REDACTED***"
            else:
                out[key] = value
        return out

    @staticmethod
    def _parse_body(raw_body: bytes, headers: Dict[str, str]) -> Any:
        text = raw_body.decode("utf-8", errors="replace")
        content_type = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        if self.mode == OperatingMode.AIRGAPPED:
            raise AirgapViolationError(
                f"Outbound call blocked for {self.provider_id}: client is in AIRGAPPED mode"
            )

        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Circuit is OPEN for provider {self.provider_id}")

        if self.rate_limiter is not None:
            self.rate_limiter.wait()

        request_headers = dict(headers or {})
        data = body
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            joiner = "&" if urllib.parse.urlparse(url).query else "?"
            url = f"{url}{joiner}{query}"

        attempt = 0
        while True:
            start = time.perf_counter()
            req = urllib.request.Request(url=url, method=method.upper(), headers=request_headers, data=data)
            status_code = 0
            response_headers: Dict[str, str] = {}
            parsed_body: Any = ""
            error_detail = ""

            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    status_code = int(response.status)
                    response_headers = dict(response.headers.items())
                    parsed_body = self._parse_body(response.read(), response_headers)

                latency_ms = (time.perf_counter() - start) * 1000.0
                result = {
                    "status_code": status_code,
                    "body": parsed_body,
                    "headers": response_headers,
                    "latency_ms": latency_ms,
                }

                if status_code >= 500:
                    raise ProviderFetchError(f"Server error {status_code}")

                self.circuit_breaker.record_success()
                self.logger.info(
                    {
                        "event": "provider_http_call",
                        "provider_id": self.provider_id,
                        "method": method.upper(),
                        "url": url,
                        "request_headers": self._sanitize_headers(request_headers),
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "attempt": attempt + 1,
                    }
                )
                return result

            except urllib.error.HTTPError as exc:
                status_code = int(exc.code)
                response_headers = dict(exc.headers.items()) if exc.headers else {}
                parsed_body = self._parse_body(exc.read() if exc.fp else b"", response_headers)
                latency_ms = (time.perf_counter() - start) * 1000.0
                error_detail = f"HTTPError {status_code}"

                if status_code < 500:
                    self.circuit_breaker.record_failure()
                    self.logger.error(
                        {
                            "event": "provider_http_call",
                            "provider_id": self.provider_id,
                            "method": method.upper(),
                            "url": url,
                            "request_headers": self._sanitize_headers(request_headers),
                            "status_code": status_code,
                            "latency_ms": latency_ms,
                            "attempt": attempt + 1,
                            "error": error_detail,
                        }
                    )
                    return {
                        "status_code": status_code,
                        "body": parsed_body,
                        "headers": response_headers,
                        "latency_ms": latency_ms,
                    }

            except (urllib.error.URLError, TimeoutError, ProviderFetchError) as exc:
                latency_ms = (time.perf_counter() - start) * 1000.0
                error_detail = str(exc)

            self.circuit_breaker.record_failure()
            self.logger.warning(
                {
                    "event": "provider_http_retry",
                    "provider_id": self.provider_id,
                    "method": method.upper(),
                    "url": url,
                    "request_headers": self._sanitize_headers(request_headers),
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                    "error": error_detail,
                }
            )

            if attempt >= self.max_retries:
                raise ProviderFetchError(
                    f"Request failed for provider {self.provider_id} after {attempt + 1} attempts: {error_detail}"
                )

            sleep_for = (2**attempt) + random.uniform(0.0, 0.25)
            time.sleep(sleep_for)
            attempt += 1
