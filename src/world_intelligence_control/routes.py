"""FastAPI routes for World Intelligence dual-source runtime control.

Military/tactical context:
These routes enforce a sovereign gateway where S3M-GUI receives intelligence
through S3M-Core only, with deterministic fallback during degraded conditions.
"""

from __future__ import annotations

from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .external_worldmonitor_adapter import ExternalWorldMonitorAdapter, ProxyResult
from .models import (
    WorldIntelligenceMode,
    WorldIntelligenceSource,
    WorldIntelligenceStatus,
)
from .runtime_manager import RuntimeManager
from .source_manager import SourceManager


world_intelligence_router = APIRouter(tags=["World Intelligence Control"])

_runtime_manager = RuntimeManager()
_external_adapter = ExternalWorldMonitorAdapter()
_source_manager = SourceManager(_runtime_manager, _external_adapter.fallback_health)


def _client_key(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "global"


def _offline_safe_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": WorldIntelligenceMode.OFFLINE_SAFE.value,
        "source": WorldIntelligenceSource.OFFLINE_SAFE.value,
        "status": "unavailable",
        "reason": reason,
    }


def _proxy_local_runtime(path: str, query_params: dict[str, Any] | None = None) -> Response:
    safe_path = (path or "").strip().lstrip("/")
    if safe_path.startswith("http://") or safe_path.startswith("https://") or ".." in safe_path:
        raise HTTPException(status_code=400, detail="invalid local runtime path")
    url = f"{_runtime_manager.local_runtime_url}/{safe_path}".rstrip("/")
    if not safe_path:
        url = f"{_runtime_manager.local_runtime_url}/"

    try:
        response = requests.get(
            url,
            params=query_params or {},
            timeout=_runtime_manager.request_timeout_seconds,
            stream=True,
        )
        body = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > 1_500_000:
                raise HTTPException(status_code=502, detail="local runtime response exceeded size limit")
        return Response(
            content=bytes(body),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers={"x-world-intelligence-source": WorldIntelligenceSource.LOCAL_SELF_HOSTED.value},
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"local runtime unavailable: {exc}") from exc


def _build_status(client_key: str) -> WorldIntelligenceStatus:
    local_health = _runtime_manager.local_runtime_health()
    decision = _source_manager.resolve_source(client_key=client_key)
    return WorldIntelligenceStatus(
        service=_runtime_manager.service_name,
        mode=decision.mode,
        active_source=decision.source,
        reason=decision.reason,
        local_runtime=local_health,
        fallback_available=decision.fallback_available,
        training_safe=decision.training_safe,
        fallback_enabled=_runtime_manager.fallback_enabled,
    )


@world_intelligence_router.get("/api/world-intelligence/status")
async def world_intelligence_status(request: Request) -> dict[str, Any]:
    return _build_status(client_key=_client_key(request)).model_dump()


@world_intelligence_router.get("/api/world-intelligence/health")
async def world_intelligence_health(request: Request) -> dict[str, Any]:
    status = _build_status(client_key=_client_key(request))
    healthy = status.active_source != WorldIntelligenceSource.OFFLINE_SAFE
    payload = status.model_dump()
    payload["healthy"] = healthy
    return payload


@world_intelligence_router.post("/api/world-intelligence/mode/local")
async def set_local_mode(request: Request) -> dict[str, Any]:
    _runtime_manager.set_mode(WorldIntelligenceMode.LOCAL_SELF_HOSTED)
    start_result, local_health = _runtime_manager.start_local_runtime()
    decision = _source_manager.resolve_source(client_key=_client_key(request))

    payload = {
        "mode": WorldIntelligenceMode.LOCAL_SELF_HOSTED.value,
        "requested_source": WorldIntelligenceSource.LOCAL_SELF_HOSTED.value,
        "active_source": decision.source.value,
        "local_runtime_action": start_result.model_dump(),
        "local_runtime": local_health.model_dump(),
    }
    if start_result.ok and local_health.healthy:
        payload["status"] = "ok"
        payload["reason"] = "local runtime started and passed health check"
        return payload

    payload["status"] = "degraded"
    payload["reason"] = "local runtime failed to become healthy; external fallback remains active when available"
    return JSONResponse(status_code=503, content=payload)


@world_intelligence_router.post("/api/world-intelligence/mode/external-fallback")
async def set_external_fallback_mode() -> dict[str, Any]:
    _runtime_manager.set_mode(WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK)
    return {"mode": WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK.value, "status": "ok"}


@world_intelligence_router.post("/api/world-intelligence/mode/training-safe")
async def set_training_safe_mode() -> dict[str, Any]:
    result = _runtime_manager.set_mode(WorldIntelligenceMode.TRAINING_SAFE)
    return {
        "mode": WorldIntelligenceMode.TRAINING_SAFE.value,
        "status": "ok",
        "local_runtime_action": result.model_dump() if result else None,
    }


@world_intelligence_router.post("/api/world-intelligence/restart-local")
async def restart_local_runtime() -> dict[str, Any]:
    result = _runtime_manager.restart_local_runtime()
    status_code = 200 if result.ok else 409
    return JSONResponse(status_code=status_code, content=result.model_dump())


@world_intelligence_router.get("/api/world-intelligence/source")
async def world_intelligence_source(request: Request) -> dict[str, Any]:
    decision = _source_manager.resolve_source(client_key=_client_key(request))
    return decision.model_dump()


@world_intelligence_router.get("/api/world-intelligence/fallback/health")
async def fallback_health(request: Request) -> dict[str, Any]:
    payload = _external_adapter.fallback_health(client_key=_client_key(request))
    status_code = 429 if payload.get("status") == "rate_limited" else 200
    return JSONResponse(status_code=status_code, content=payload)


@world_intelligence_router.get("/api/world-intelligence/fallback/bootstrap")
async def fallback_bootstrap(request: Request) -> dict[str, Any]:
    status_code, payload = _external_adapter.fallback_bootstrap(client_key=_client_key(request))
    return JSONResponse(status_code=status_code, content=payload)


@world_intelligence_router.get("/api/world-intelligence/fallback/feed")
async def fallback_feed(request: Request) -> dict[str, Any]:
    status_code, payload = _external_adapter.fallback_feed(client_key=_client_key(request))
    return JSONResponse(status_code=status_code, content=payload)


def _runtime_gateway(path: str, request: Request) -> Response:
    decision = _source_manager.resolve_source(client_key=_client_key(request))
    params = dict(request.query_params)

    if decision.source == WorldIntelligenceSource.LOCAL_SELF_HOSTED:
        return _proxy_local_runtime(path, params)

    if decision.source == WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK:
        proxy_result = _external_adapter.proxy_runtime(path=path, query_params=params, client_key=_client_key(request))
        if isinstance(proxy_result, dict):
            status_code = 429 if proxy_result.get("status") == "rate_limited" else 503
            return JSONResponse(status_code=status_code, content=proxy_result)
        assert isinstance(proxy_result, ProxyResult)
        return Response(
            content=proxy_result.content,
            status_code=proxy_result.status_code,
            media_type=proxy_result.content_type,
            headers={"x-world-intelligence-source": WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK.value},
        )

    return JSONResponse(
        status_code=503,
        content=_offline_safe_payload("local runtime and external fallback are unavailable"),
    )


@world_intelligence_router.get("/world-intelligence/runtime/")
async def runtime_proxy_root(request: Request) -> Response:
    return _runtime_gateway(path="", request=request)


@world_intelligence_router.get("/world-intelligence/runtime/{path:path}")
async def runtime_proxy(path: str, request: Request) -> Response:
    return _runtime_gateway(path=path, request=request)
