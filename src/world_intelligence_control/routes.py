"""FastAPI routes for World Intelligence dual-source runtime control.

Military/tactical context:
These routes enforce a sovereign gateway where S3M-GUI receives intelligence
through S3M-Core only, with deterministic fallback during degraded conditions.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import unquote

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
LOGGER = logging.getLogger(__name__)

RUNTIME_MOUNT_PATH = "/world-intelligence/runtime"
UPSTREAM_MOUNT_PATH = "/world-intelligence/upstream"
_MAX_LOCAL_RUNTIME_RESPONSE_BYTES = 25 * 1024 * 1024
_MAX_UPSTREAM_PROXY_RESPONSE_BYTES = 10 * 1024 * 1024
_RUNTIME_REWRITE_PREFIXES = ("assets/", "favico/", "manifest", "service-worker", "sw")
_UPSTREAM_PROXY_ORIGINS = {
    "api": "https://api.worldmonitor.app",
    "maps": "https://maps.worldmonitor.app",
    "clerk": "https://clerk.worldmonitor.app",
    "abacus": "https://abacus.worldmonitor.app",
}
_EXTERNAL_RUNTIME_ORIGIN_REWRITES = {
    origin: f"{UPSTREAM_MOUNT_PATH}/{name}" for name, origin in _UPSTREAM_PROXY_ORIGINS.items()
}
_HTML_RUNTIME_URL_RE = re.compile(
    r"(?P<prefix>\b(?:src|href)=['\"])(?P<path>/(?:assets/|favico/|manifest|service-worker|sw)[^'\"]*)"
)
_COMPRESSED_SUFFIX_CONTENT_ENCODING = {
    ".br": "br",
    ".gz": "gzip",
}
_CONTENT_TYPE_BY_EXTENSION = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".wasm": "application/wasm",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}
_IFRAME_BLOCKING_HEADERS = {
    "x-frame-options",
    "cross-origin-embedder-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
    "origin-agent-cluster",
    "set-cookie",
}
_REWRITABLE_TEXT_CONTENT_TYPES = {
    "application/ecmascript",
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/x-javascript",
    "text/css",
    "text/ecmascript",
    "text/html",
    "text/javascript",
    "text/plain",
}
_REWRITABLE_TEXT_EXTENSIONS = (".css", ".html", ".htm", ".js", ".json", ".mjs", ".txt", ".webmanifest")
_UPSTREAM_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "x-clerk-client",
    "x-clerk-js-version",
    "x-requested-with",
}
_CORS_ALLOWED_ORIGINS = {
    "https://app.abraxas-s3m.com",
    "https://s3m-gui.pages.dev",
    "http://localhost:3000",
    "http://localhost:5173",
}


def _client_key(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "global"


def _offline_safe_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": WorldIntelligenceMode.OFFLINE_SAFE.value,
        "source": WorldIntelligenceSource.OFFLINE_SAFE.value,
        "status": "unavailable",
        "reason": reason,
    }


def _normalize_runtime_path(path: str) -> str:
    raw_path = (path or "").strip()
    decoded_path = unquote(raw_path)
    if "://" in decoded_path or decoded_path.startswith("//") or "\\" in decoded_path:
        raise HTTPException(status_code=400, detail="invalid local runtime path")
    safe_path = decoded_path.lstrip("/")
    if any(segment == ".." for segment in safe_path.split("/")):
        raise HTTPException(status_code=400, detail="invalid local runtime path")
    return safe_path


def _normalize_proxy_path(path: str) -> str:
    raw_path = (path or "").strip()
    decoded_path = unquote(raw_path)
    if "://" in decoded_path or decoded_path.startswith("//") or "\\" in decoded_path:
        raise HTTPException(status_code=400, detail="invalid upstream proxy path")
    safe_path = decoded_path.lstrip("/")
    if any(segment == ".." for segment in safe_path.split("/")):
        raise HTTPException(status_code=400, detail="invalid upstream proxy path")
    return safe_path


def _charset_from_content_type(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip('"')
    return "utf-8"


def _infer_content_type(path: str, upstream_content_type: str | None) -> str:
    content_type = (upstream_content_type or "").strip()
    base_content_type = content_type.split(";", 1)[0].lower()
    if content_type and base_content_type not in {"application/octet-stream", "binary/octet-stream"}:
        return content_type

    path_without_query = path.split("?", 1)[0]
    for compressed_suffix in _COMPRESSED_SUFFIX_CONTENT_ENCODING:
        if path_without_query.endswith(compressed_suffix):
            path_without_query = path_without_query[: -len(compressed_suffix)]
            break
    if not path_without_query:
        return _CONTENT_TYPE_BY_EXTENSION[".html"]
    known_types = sorted(
        _CONTENT_TYPE_BY_EXTENSION.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for extension, inferred_type in known_types:
        if path_without_query.endswith(extension):
            return inferred_type
    return content_type or "application/octet-stream"


def _content_encoding_for_path(path: str, upstream_encoding: str | None) -> str | None:
    if upstream_encoding:
        return upstream_encoding
    path_without_query = path.split("?", 1)[0]
    for compressed_suffix, encoding in _COMPRESSED_SUFFIX_CONTENT_ENCODING.items():
        if path_without_query.endswith(compressed_suffix):
            return encoding
    return None


def _is_html_response(path: str, content_type: str) -> bool:
    base_content_type = content_type.split(";", 1)[0].lower()
    return base_content_type == "text/html" or not path or path.endswith((".html", ".htm"))


def _is_rewritable_text_response(path: str, content_type: str, content_encoding: str | None) -> bool:
    if content_encoding:
        return False
    base_content_type = content_type.split(";", 1)[0].lower()
    if base_content_type in _REWRITABLE_TEXT_CONTENT_TYPES:
        return True
    path_without_query = path.split("?", 1)[0]
    return path_without_query.endswith(_REWRITABLE_TEXT_EXTENSIONS)


def _rewrite_runtime_html(html: str) -> tuple[str, int]:
    rewrite_count = 0

    def should_rewrite(url_path: str) -> bool:
        stripped = url_path.lstrip("/")
        if stripped.startswith(("assets/", "favico/", "service-worker")):
            return True
        if stripped == "manifest" or stripped.startswith(("manifest.", "manifest?", "manifest/")):
            return True
        return stripped == "sw" or stripped.startswith(("sw.", "sw?", "sw/"))

    def replace(match: re.Match[str]) -> str:
        nonlocal rewrite_count
        url_path = match.group("path")
        if not should_rewrite(url_path):
            return match.group(0)
        if url_path.startswith(f"{RUNTIME_MOUNT_PATH}/"):
            return match.group(0)
        rewrite_count += 1
        return f"{match.group('prefix')}{RUNTIME_MOUNT_PATH}{url_path}"

    return _HTML_RUNTIME_URL_RE.sub(replace, html), rewrite_count


def _rewrite_external_runtime_origins(content: str) -> tuple[str, int]:
    rewrite_count = 0
    rewritten = content
    for origin, proxy_path in _EXTERNAL_RUNTIME_ORIGIN_REWRITES.items():
        sources = (
            origin,
            origin.replace("/", r"\/"),
            f"//{origin.removeprefix('https://')}",
        )
        for source in sources:
            count = rewritten.count(source)
            if count:
                rewritten = rewritten.replace(source, proxy_path)
                rewrite_count += count
    return rewritten, rewrite_count


def _sanitize_csp_header(value: str) -> str | None:
    directives = []
    for directive in value.split(";"):
        stripped = directive.strip()
        if not stripped:
            continue
        directive_name = stripped.split(None, 1)[0].lower()
        if directive_name == "frame-ancestors":
            continue
        directives.append(stripped)
    return "; ".join(directives) if directives else None


def _iter_upstream_body(response: requests.Response):
    raw_stream = getattr(response, "raw", None)
    if raw_stream is not None and hasattr(raw_stream, "stream"):
        return raw_stream.stream(8192, decode_content=False)
    return response.iter_content(chunk_size=8192)


def _runtime_response_headers(
    upstream_headers: dict[str, str],
    source: WorldIntelligenceSource,
    path: str,
    content_type: str,
    rewrite_count: int,
    origin_rewrite_count: int,
) -> dict[str, str]:
    headers = {
        "x-world-intelligence-source": source.value,
        "x-world-intelligence-runtime-path": path or "/",
        "x-world-intelligence-html-rewrites": str(rewrite_count),
        "x-world-intelligence-origin-rewrites": str(origin_rewrite_count),
        "content-type": content_type,
    }
    for header_name in ("cache-control", "etag", "last-modified"):
        header_value = upstream_headers.get(header_name)
        if header_value:
            headers[header_name] = header_value
    content_encoding = _content_encoding_for_path(path, upstream_headers.get("content-encoding"))
    if content_encoding:
        headers["content-encoding"] = content_encoding
    return {
        header_name: header_value
        for header_name, header_value in headers.items()
        if header_name.lower() not in _HOP_BY_HOP_HEADERS | _IFRAME_BLOCKING_HEADERS
    }


def _build_runtime_response(
    *,
    content: bytes,
    status_code: int,
    upstream_headers: dict[str, str],
    source: WorldIntelligenceSource,
    path: str,
    method: str,
) -> Response:
    upstream_headers = {
        header_name.lower(): header_value
        for header_name, header_value in upstream_headers.items()
    }
    content_type = _infer_content_type(path, upstream_headers.get("content-type"))
    rewrite_count = 0
    origin_rewrite_count = 0
    body = content
    content_encoding = _content_encoding_for_path(path, upstream_headers.get("content-encoding"))
    if (
        method != "HEAD"
        and status_code < 400
        and _is_rewritable_text_response(path, content_type, content_encoding)
    ):
        charset = _charset_from_content_type(content_type)
        rewritten_text = content.decode(charset, errors="replace")
        if _is_html_response(path, content_type):
            rewritten_text, rewrite_count = _rewrite_runtime_html(rewritten_text)
        rewritten_text, origin_rewrite_count = _rewrite_external_runtime_origins(rewritten_text)
        body = rewritten_text.encode(charset)

    headers = _runtime_response_headers(
        upstream_headers=upstream_headers,
        source=source,
        path=path,
        content_type=content_type,
        rewrite_count=rewrite_count,
        origin_rewrite_count=origin_rewrite_count,
    )
    return Response(
        content=b"" if method == "HEAD" else body,
        status_code=status_code,
        headers=headers,
    )


def _proxy_local_runtime(
    path: str,
    query_params: dict[str, Any] | None = None,
    method: str = "GET",
) -> Response:
    safe_path = _normalize_runtime_path(path)
    url = f"{_runtime_manager.local_runtime_url}/{safe_path}".rstrip("/")
    if not safe_path:
        url = f"{_runtime_manager.local_runtime_url}/"

    try:
        response = requests.request(
            method,
            url,
            params=query_params or {},
            headers={"Accept-Encoding": "identity"},
            timeout=_runtime_manager.request_timeout_seconds,
            stream=True,
        )
        body = bytearray()
        if method != "HEAD":
            for chunk in _iter_upstream_body(response):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > _MAX_LOCAL_RUNTIME_RESPONSE_BYTES:
                    raise HTTPException(status_code=502, detail="local runtime response exceeded size limit")
        LOGGER.info(
            "world intelligence local runtime proxy path=%s status=%s content_type=%s bytes=%s",
            safe_path or "/",
            response.status_code,
            response.headers.get("content-type", ""),
            len(body),
        )
        return _build_runtime_response(
            content=bytes(body),
            status_code=response.status_code,
            upstream_headers=dict(response.headers),
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            path=safe_path,
            method=method,
        )
    except requests.RequestException as exc:
        LOGGER.warning("world intelligence local runtime unavailable path=%s error=%s", safe_path or "/", exc)
        raise HTTPException(status_code=503, detail=f"local runtime unavailable: {exc}") from exc


def _build_status(client_key: str) -> WorldIntelligenceStatus:
    local_health = _runtime_manager.local_runtime_health()
    decision = _source_manager.resolve_source(client_key=client_key)
    return WorldIntelligenceStatus(
        service=_runtime_manager.service_name,
        mode=decision.mode,
        active_source=decision.source,
        reason=decision.reason,
        configured_local_url=_runtime_manager.local_runtime_url,
        local_runtime_healthy=decision.local_runtime_healthy,
        systemd_control_available=_runtime_manager.systemd_control_available(),
        local_runtime=local_health,
        fallback_available=decision.fallback_available,
        training_safe=decision.training_safe,
        fallback_enabled=_runtime_manager.fallback_enabled,
    )


def _runtime_url_for_source(source: WorldIntelligenceSource) -> str | None:
    if source == WorldIntelligenceSource.LOCAL_SELF_HOSTED:
        return _runtime_manager.local_runtime_url
    if source == WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK:
        return "https://www.worldmonitor.app"
    return None


def _cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin", "")
    headers = {
        "access-control-allow-methods": "GET, POST, OPTIONS",
        "access-control-allow-headers": request.headers.get(
            "access-control-request-headers",
            "accept, authorization, content-type, x-requested-with",
        ),
        "access-control-max-age": "600",
        "vary": "origin",
    }
    if origin in _CORS_ALLOWED_ORIGINS:
        headers["access-control-allow-origin"] = origin
    return headers


def _safe_header_value(value: str) -> str:
    return value.replace("\r", "").replace("\n", "").strip()


def _upstream_request_headers(request: Request) -> dict[str, str]:
    headers = {
        "Accept-Encoding": "identity",
        "User-Agent": "S3M-WorldIntelligenceGateway/1.0",
    }
    for header_name, header_value in request.headers.items():
        normalized_name = header_name.lower()
        if normalized_name not in _UPSTREAM_REQUEST_HEADERS:
            continue
        safe_value = _safe_header_value(header_value)
        if safe_value:
            headers[header_name] = safe_value
    return headers


def _sanitized_proxy_response_headers(
    upstream_headers: dict[str, str],
    content_type: str,
    path: str,
    origin_rewrite_count: int,
    request: Request,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "content-type": content_type,
        "x-world-intelligence-upstream-origin-rewrites": str(origin_rewrite_count),
    }
    for header_name, header_value in upstream_headers.items():
        normalized_name = header_name.lower()
        if normalized_name in _HOP_BY_HOP_HEADERS | _IFRAME_BLOCKING_HEADERS:
            continue
        if normalized_name == "content-security-policy":
            sanitized_csp = _sanitize_csp_header(header_value)
            if sanitized_csp:
                headers[normalized_name] = sanitized_csp
            continue
        if normalized_name in {"cache-control", "etag", "expires", "last-modified", "vary"}:
            headers[normalized_name] = header_value
    content_encoding = _content_encoding_for_path(path, upstream_headers.get("content-encoding"))
    if content_encoding:
        headers["content-encoding"] = content_encoding
    headers.update(_cors_headers(request))
    return headers


def _upstream_url(origin: str, path: str, request: Request) -> str:
    safe_path = _normalize_proxy_path(path)
    url = f"{origin}/{safe_path}".rstrip("/")
    if not safe_path:
        url = f"{origin}/"
    raw_query = request.scope.get("query_string", b"")
    if raw_query:
        url = f"{url}?{raw_query.decode('latin-1')}"
    return url


async def _upstream_proxy_gateway(upstream_name: str, path: str, request: Request) -> Response:
    origin = _UPSTREAM_PROXY_ORIGINS.get(upstream_name)
    if origin is None:
        raise HTTPException(status_code=404, detail="unknown World Intelligence upstream")

    if request.method.upper() == "OPTIONS":
        return Response(status_code=204, headers=_cors_headers(request))

    body = await request.body()
    url = _upstream_url(origin, path, request)
    try:
        response = requests.request(
            request.method.upper(),
            url,
            data=body if body else None,
            headers=_upstream_request_headers(request),
            timeout=_external_adapter.timeout_seconds,
            stream=True,
            allow_redirects=False,
        )
        upstream_headers = {k.lower(): v for k, v in response.headers.items()}
        content_type = _infer_content_type(path, upstream_headers.get("content-type"))
        response_body = bytearray()
        for chunk in _iter_upstream_body(response):
            if not chunk:
                continue
            response_body.extend(chunk)
            if len(response_body) > _MAX_UPSTREAM_PROXY_RESPONSE_BYTES:
                raise HTTPException(status_code=502, detail="upstream response exceeded size limit")

        origin_rewrite_count = 0
        content_encoding = _content_encoding_for_path(path, upstream_headers.get("content-encoding"))
        payload = bytes(response_body)
        if response.status_code < 400 and _is_rewritable_text_response(path, content_type, content_encoding):
            charset = _charset_from_content_type(content_type)
            rewritten_text, origin_rewrite_count = _rewrite_external_runtime_origins(
                payload.decode(charset, errors="replace")
            )
            payload = rewritten_text.encode(charset)

        headers = _sanitized_proxy_response_headers(
            upstream_headers=upstream_headers,
            content_type=content_type,
            path=path,
            origin_rewrite_count=origin_rewrite_count,
            request=request,
        )
        LOGGER.info(
            "world intelligence upstream proxy upstream=%s path=%s status=%s bytes=%s",
            upstream_name,
            path or "/",
            response.status_code,
            len(payload),
        )
        return Response(content=payload, status_code=response.status_code, headers=headers)
    except requests.RequestException as exc:
        LOGGER.warning(
            "world intelligence upstream proxy unavailable upstream=%s path=%s error=%s",
            upstream_name,
            path,
            exc,
        )
        raise HTTPException(status_code=502, detail=f"World Intelligence upstream unavailable: {exc}") from exc


@world_intelligence_router.get("/api/world-intelligence/status")
async def world_intelligence_status(request: Request) -> dict[str, Any]:
    return _build_status(client_key=_client_key(request)).model_dump()


@world_intelligence_router.get("/api/world-intelligence/health")
async def world_intelligence_health(request: Request) -> dict[str, Any]:
    status = _build_status(client_key=_client_key(request))
    healthy = status.active_source != WorldIntelligenceSource.OFFLINE_SAFE
    payload = status.model_dump()
    payload["healthy"] = healthy
    payload["runtime_proxy"] = {
        "mounted_path": RUNTIME_MOUNT_PATH,
        "local_upstream": _runtime_manager.local_runtime_url,
        "html_asset_rewrite": "enabled",
        "asset_proxy": "enabled",
        "safe_prefixes": list(_RUNTIME_REWRITE_PREFIXES),
    }
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
        "configured_local_url": _runtime_manager.local_runtime_url,
        "local_runtime_healthy": local_health.healthy,
        "systemd_control_available": _runtime_manager.systemd_control_available(),
        "fallback_available": decision.fallback_available,
        "local_runtime_action": start_result.model_dump(),
        "local_runtime": local_health.model_dump(),
    }
    if local_health.healthy:
        payload["status"] = "ok"
        if start_result.ok:
            payload["reason"] = "local runtime started and passed health check"
        else:
            payload["reason"] = "local runtime health check passed; systemd control unavailable from API container"
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
    payload = decision.model_dump()
    payload["active_source"] = decision.source.value
    payload["configured_local_url"] = _runtime_manager.local_runtime_url
    payload["local_runtime_health_url"] = decision.local_runtime_health_url or _runtime_manager.local_runtime_url
    payload["local_runtime_healthy"] = decision.local_runtime_healthy
    payload["systemd_control_available"] = _runtime_manager.systemd_control_available()
    payload["fallback_available"] = decision.fallback_available
    payload["runtime_url_selected"] = _runtime_url_for_source(decision.source)
    return payload


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


@world_intelligence_router.api_route("/world-intelligence/upstream/api", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/api/", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/api/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def upstream_api_proxy(request: Request, path: str = "") -> Response:
    return await _upstream_proxy_gateway("api", path, request)


@world_intelligence_router.api_route("/world-intelligence/upstream/maps", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/maps/", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/maps/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def upstream_maps_proxy(request: Request, path: str = "") -> Response:
    return await _upstream_proxy_gateway("maps", path, request)


@world_intelligence_router.api_route("/world-intelligence/upstream/clerk", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/clerk/", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/clerk/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def upstream_clerk_proxy(request: Request, path: str = "") -> Response:
    return await _upstream_proxy_gateway("clerk", path, request)


@world_intelligence_router.api_route("/world-intelligence/upstream/abacus", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/abacus/", methods=["GET", "POST", "OPTIONS"])
@world_intelligence_router.api_route("/world-intelligence/upstream/abacus/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def upstream_abacus_proxy(request: Request, path: str = "") -> Response:
    return await _upstream_proxy_gateway("abacus", path, request)


def _runtime_gateway(path: str, request: Request) -> Response:
    decision = _source_manager.resolve_source(client_key=_client_key(request))
    params = dict(request.query_params)
    method = request.method.upper()

    if decision.source == WorldIntelligenceSource.LOCAL_SELF_HOSTED:
        return _proxy_local_runtime(path, params, method=method)

    if decision.source == WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK:
        proxy_result = _external_adapter.proxy_runtime(path=path, query_params=params, client_key=_client_key(request))
        if isinstance(proxy_result, dict):
            status_code = 429 if proxy_result.get("status") == "rate_limited" else 503
            return JSONResponse(status_code=status_code, content=proxy_result)
        assert isinstance(proxy_result, ProxyResult)
        return _build_runtime_response(
            content=proxy_result.content,
            status_code=proxy_result.status_code,
            upstream_headers={"content-type": proxy_result.content_type},
            source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
            path=path,
            method=method,
        )

    return JSONResponse(
        status_code=503,
        content=_offline_safe_payload("local runtime and external fallback are unavailable"),
    )


@world_intelligence_router.get("/world-intelligence/runtime/")
@world_intelligence_router.head("/world-intelligence/runtime/")
async def runtime_proxy_root(request: Request) -> Response:
    return _runtime_gateway(path="", request=request)


@world_intelligence_router.get("/world-intelligence/runtime/{path:path}")
@world_intelligence_router.head("/world-intelligence/runtime/{path:path}")
async def runtime_proxy(path: str, request: Request) -> Response:
    return _runtime_gateway(path=path, request=request)
