"""FastAPI/Starlette security middleware for S3M Phase 10.

This middleware enforces zero-trust controls at API ingress for tactical
deployments where edge nodes may be contested and require strict request
validation before mission services execute.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Dict, List, Optional

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.security.crypto import ClassificationBanner, SecureAuditLog
from src.security.input_validator import InputValidator


class SecurityMiddleware(BaseHTTPMiddleware):
    """Cross-cutting API middleware for auth, throttling, and auditing."""

    _AUTH_BYPASS_PATHS = ("/health", "/docs", "/redoc", "/dashboard/")

    def __init__(self, app, config: Optional[dict] = None):  # type: ignore[override]
        super().__init__(app)
        cfg = config or {}
        self.config = {
            "auth_enabled": bool(cfg.get("auth_enabled", False)),
            "api_key": str(cfg.get("api_key", "CHANGEME")),
            "rate_limit_enabled": bool(cfg.get("rate_limit_enabled", True)),
            "rate_limit_rpm": int(cfg.get("rate_limit_rpm", 120)),
            "sanitize_inputs": bool(cfg.get("sanitize_inputs", True)),
            "cors_lockdown": bool(cfg.get("cors_lockdown", False)),
            "audit_security_events": bool(cfg.get("audit_security_events", True)),
        }

        self.rate_limit_store: Dict[str, List[float]] = {}
        self.rate_limit_lock = Lock()
        self.audit_log = SecureAuditLog()
        self.banner = ClassificationBanner()

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        auth_status = "bypassed"
        client_ip = self._client_ip(request)

        # 1) Authentication
        if self.config["auth_enabled"] and not self._is_auth_bypass_path(request.url.path):
            incoming_api_key = request.headers.get("X-API-Key", "")
            if incoming_api_key != self.config["api_key"]:
                auth_status = "failed"
                response = JSONResponse(status_code=401, content={"detail": "Unauthorized"})
                return self._finalize_response(
                    request=request,
                    response=response,
                    start=start,
                    client_ip=client_ip,
                    auth_status=auth_status,
                )
            auth_status = "ok"

        # 2) Rate limiting
        if self.config["rate_limit_enabled"]:
            if not self._allow_request(client_ip):
                response = JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
                return self._finalize_response(
                    request=request,
                    response=response,
                    start=start,
                    client_ip=client_ip,
                    auth_status=auth_status,
                )

        # 3) Input sanitization / inspection
        if self.config["sanitize_inputs"]:
            safe, reason = await InputValidator.sanitize_request(request)
            if not safe:
                response = JSONResponse(status_code=400, content={"detail": f"Dangerous input detected: {reason}"})
                return self._finalize_response(
                    request=request,
                    response=response,
                    start=start,
                    client_ip=client_ip,
                    auth_status=auth_status,
                )

        # 6) Call underlying handler
        response = await call_next(request)
        return self._finalize_response(
            request=request,
            response=response,
            start=start,
            client_ip=client_ip,
            auth_status=auth_status,
        )

    def _finalize_response(
        self,
        *,
        request: Request,
        response: Response,
        start: float,
        client_ip: str,
        auth_status: str,
    ) -> Response:
        # 5) Classification banner header
        self.banner.inject_header(response)
        latency_ms = round((time.perf_counter() - start) * 1000.0, 3)

        # 4 + 7) Audit trail
        if self.config["audit_security_events"]:
            self.audit_log.log(
                action="http_request",
                severity="INFO",
                source="middleware",
                details={
                    "timestamp": time.time(),
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "auth_status": auth_status,
                },
            )
        return response

    def _is_auth_bypass_path(self, path: str) -> bool:
        for prefix in self._AUTH_BYPASS_PATHS:
            if path.startswith(prefix):
                return True
        return False

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _allow_request(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - 60.0
        max_per_minute = max(1, int(self.config["rate_limit_rpm"]))

        with self.rate_limit_lock:
            timestamps = self.rate_limit_store.get(client_ip, [])
            timestamps = [ts for ts in timestamps if ts >= window_start]
            if len(timestamps) >= max_per_minute:
                self.rate_limit_store[client_ip] = timestamps
                return False
            timestamps.append(now)
            self.rate_limit_store[client_ip] = timestamps
            return True
