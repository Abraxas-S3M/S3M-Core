"""Unit tests for World Intelligence dual-source runtime control."""

from __future__ import annotations

import gzip
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.world_intelligence_control.external_worldmonitor_adapter import (
    ExternalWorldMonitorAdapter,
    ProxyResult,
)
from src.world_intelligence_control.models import (
    LocalRuntimeHealth,
    ServiceActionResult,
    SourceDecision,
    WorldIntelligenceMode,
    WorldIntelligenceSource,
)
from src.world_intelligence_control.routes import world_intelligence_router
from src.world_intelligence_control.runtime_manager import RuntimeManager
from src.world_intelligence_control.source_manager import SourceManager


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        body: bytes = b'{"ok": true}',
        content_type: str = "application/json",
        url: str = "https://api.worldmonitor.app/health",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {"content-type": content_type}
        self.url = url

    def iter_content(self, chunk_size: int = 8192):
        _ = chunk_size
        yield self._body


def test_runtime_manager_training_safe_stops_local(monkeypatch) -> None:
    _ = monkeypatch
    calls: list[tuple[str, str]] = []

    def runner(action: str, service: str):
        calls.append((action, service))
        return ServiceActionResult(ok=True, action=action, service=service, detail="ok")

    manager = RuntimeManager(service_runner=runner)

    # The test uses explicit mode control to enforce training-safe halt.
    result = manager.set_mode(WorldIntelligenceMode.TRAINING_SAFE)
    assert result is not None
    assert calls[0][0] == "stop"
    blocked_restart = manager.restart_local_runtime()
    assert blocked_restart.ok is False


def test_runtime_manager_uses_configured_local_url(monkeypatch) -> None:
    monkeypatch.setenv("WORLD_INTELLIGENCE_LOCAL_URL", "http://172.17.0.1:8095/")

    manager = RuntimeManager()

    assert manager.local_runtime_url == "http://172.17.0.1:8095"


def test_runtime_manager_defaults_to_container_host_local_url(monkeypatch) -> None:
    monkeypatch.delenv("WORLD_INTELLIGENCE_LOCAL_URL", raising=False)

    manager = RuntimeManager()

    assert manager.local_runtime_url == "http://172.17.0.1:8095"


def test_runtime_manager_reports_systemd_unavailable_in_container(monkeypatch) -> None:
    monkeypatch.setattr("src.world_intelligence_control.runtime_manager.shutil.which", lambda name: None)

    def missing_systemctl(*args: Any, **kwargs: Any):
        _ = args, kwargs
        raise FileNotFoundError()

    monkeypatch.setattr("src.world_intelligence_control.runtime_manager.subprocess.run", missing_systemctl)
    manager = RuntimeManager(local_runtime_url="http://172.17.0.1:8095")

    result = manager.restart_local_runtime()

    assert manager.systemd_control_available() is False
    assert result.ok is False
    assert result.detail == "systemctl unavailable in API container"


def test_source_manager_switches_to_fallback_when_local_down() -> None:
    manager = RuntimeManager()
    manager.set_mode(WorldIntelligenceMode.LOCAL_SELF_HOSTED)
    manager.local_runtime_health = lambda: LocalRuntimeHealth(  # type: ignore[method-assign]
        healthy=False,
        status="down",
        endpoint="http://172.17.0.1:8095",
        detail="down",
    )
    source_manager = SourceManager(manager, lambda client_key="global": {"available": True})
    decision = source_manager.resolve_source()
    assert decision.source == WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK


def test_source_manager_keeps_healthy_local_runtime_in_external_mode() -> None:
    manager = RuntimeManager()
    manager.set_mode(WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK)
    manager.local_runtime_health = lambda: LocalRuntimeHealth(  # type: ignore[method-assign]
        healthy=True,
        status="healthy",
        endpoint="http://172.17.0.1:8095",
        status_code=200,
        detail="local runtime responded",
    )
    source_manager = SourceManager(manager, lambda client_key="global": {"available": True})

    decision = source_manager.resolve_source()

    assert decision.source == WorldIntelligenceSource.LOCAL_SELF_HOSTED
    assert decision.local_runtime_healthy is True
    assert decision.fallback_available is True
    assert decision.training_safe is False


def test_external_adapter_enforces_allowlist() -> None:
    adapter = ExternalWorldMonitorAdapter()
    try:
        adapter._enforce_allowlist("https://example.com/path")  # noqa: SLF001
        assert False, "allowlist check should fail"
    except ValueError:
        assert True


def test_external_adapter_bootstrap_uses_bounded_response(monkeypatch) -> None:
    adapter = ExternalWorldMonitorAdapter(max_response_bytes=64 * 1024)

    def fake_get(*args: Any, **kwargs: Any):
        _ = args, kwargs
        return _FakeResponse(
            status_code=200,
            body=b'{"summary": "ok"}',
            content_type="application/json",
            url="https://www.worldmonitor.app/",
        )

    monkeypatch.setattr("requests.get", fake_get)
    status_code, payload = adapter.fallback_bootstrap()
    assert status_code == 200
    assert payload["status"] == "ok"


def test_world_intelligence_routes_runtime_offline_safe(monkeypatch) -> None:
    _ = monkeypatch
    from src.world_intelligence_control import routes as module_routes

    module_routes._source_manager.resolve_source = lambda client_key="global": SourceDecision(  # type: ignore[method-assign]
        mode=WorldIntelligenceMode.OFFLINE_SAFE,
        source=WorldIntelligenceSource.OFFLINE_SAFE,
        reason="offline",
        local_runtime_healthy=False,
        fallback_available=False,
        training_safe=False,
    )
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)
    response = client.get("/world-intelligence/runtime/")
    assert response.status_code == 503
    assert response.json()["mode"] == WorldIntelligenceMode.OFFLINE_SAFE.value


def test_world_intelligence_routes_runtime_external_proxy(monkeypatch) -> None:
    _ = monkeypatch
    from src.world_intelligence_control import routes as module_routes

    module_routes._source_manager.resolve_source = lambda client_key="global": SourceDecision(  # type: ignore[method-assign]
        mode=WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK,
        source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
        reason="fallback",
        local_runtime_healthy=False,
        fallback_available=True,
        training_safe=False,
    )
    module_routes._external_adapter.proxy_runtime = lambda path, query_params, client_key="global": ProxyResult(  # type: ignore[method-assign]
        status_code=200,
        content=b"ok",
        content_type="text/plain",
        upstream_url="https://www.worldmonitor.app/",
    )
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)
    response = client.get("/world-intelligence/runtime/")
    assert response.status_code == 200
    assert response.text == "ok"


def test_local_runtime_proxy_rewrites_vite_asset_urls(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=False,
            training_safe=False,
        ),
    )
    upstream_urls: list[str] = []

    def fake_request(*args: Any, **kwargs: Any):
        method, url = args[:2]
        upstream_urls.append(f"{method} {url}")
        _ = kwargs
        html = (
            '<script type="module" src="/assets/main-DXioYkv_.js"></script>'
            '<link rel="stylesheet" href="/assets/settings-persistence-CCxf_ZvB.css">'
            '<link rel="icon" href="/favico/favicon.ico">'
            '<link rel="manifest" href="/manifest.webmanifest">'
            '<script src="/sw.js"></script>'
            '<a href="/swagger">Operator docs</a>'
        )
        return _FakeResponse(
            status_code=200,
            body=html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            url=url,
        )

    monkeypatch.setattr(module_routes.requests, "request", fake_request)
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    response = client.get("/world-intelligence/runtime/")

    assert response.status_code == 200
    assert upstream_urls == ["GET http://172.17.0.1:8095/"]
    assert 'src="/world-intelligence/runtime/assets/main-DXioYkv_.js' in response.text
    assert 'href="/world-intelligence/runtime/assets/settings-persistence-CCxf_ZvB.css' in response.text
    assert 'href="/world-intelligence/runtime/favico/favicon.ico' in response.text
    assert 'href="/world-intelligence/runtime/manifest.webmanifest' in response.text
    assert 'src="/world-intelligence/runtime/sw.js' in response.text
    assert 'href="/swagger"' in response.text
    assert response.headers["x-world-intelligence-html-rewrites"] == "5"


def test_local_runtime_proxy_rewrites_worldmonitor_origins_in_html_and_js(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=False,
            training_safe=False,
        ),
    )

    def fake_request(*args: Any, **kwargs: Any):
        method, url = args[:2]
        _ = method, kwargs
        if url.endswith("/assets/app.js"):
            body = b'fetch("https://api.worldmonitor.app/feed"); fetch("https:\\/\\/maps.worldmonitor.app\\/tiles")'
            return _FakeResponse(
                status_code=200,
                body=body,
                content_type="application/javascript; charset=utf-8",
                url=url,
            )
        html = (
            '<script src="/assets/app.js"></script>'
            '<script>window.api="https://api.worldmonitor.app"</script>'
            '<script>window.clerk="//clerk.worldmonitor.app/v1"</script>'
        )
        return _FakeResponse(
            status_code=200,
            body=html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            url=url,
        )

    monkeypatch.setattr(module_routes.requests, "request", fake_request)
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    html_response = client.get("/world-intelligence/runtime/")
    js_response = client.get("/world-intelligence/runtime/assets/app.js")

    assert html_response.status_code == 200
    assert 'src="/world-intelligence/runtime/assets/app.js' in html_response.text
    assert "/world-intelligence/upstream/api" in html_response.text
    assert "/world-intelligence/upstream/clerk/v1" in html_response.text
    assert html_response.headers["x-world-intelligence-html-rewrites"] == "1"
    assert html_response.headers["x-world-intelligence-origin-rewrites"] == "2"
    assert js_response.status_code == 200
    assert "https://api.worldmonitor.app" not in js_response.text
    assert "https:\\/\\/maps.worldmonitor.app" not in js_response.text
    assert "/world-intelligence/upstream/api/feed" in js_response.text
    assert "/world-intelligence/upstream/maps\\/tiles" in js_response.text


def test_local_runtime_proxy_preserves_nested_compressed_asset_type(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=False,
            training_safe=False,
        ),
    )
    upstream_urls: list[str] = []

    def fake_request(*args: Any, **kwargs: Any):
        method, url = args[:2]
        upstream_urls.append(f"{method} {url}")
        _ = kwargs
        return _FakeResponse(
            status_code=200,
            body=gzip.compress(b"compressed-js-bytes"),
            content_type="application/octet-stream",
            url=url,
        )

    monkeypatch.setattr(module_routes.requests, "request", fake_request)
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    response = client.get("/world-intelligence/runtime/assets/main-DXioYkv_.js.gz")

    assert response.status_code == 200
    assert upstream_urls == ["GET http://172.17.0.1:8095/assets/main-DXioYkv_.js.gz"]
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["content-encoding"] == "gzip"


def test_world_intelligence_upstream_proxy_forwards_fixed_origin_and_sanitizes_headers(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    captured: dict[str, Any] = {}

    def fake_request(*args: Any, **kwargs: Any):
        method, url = args[:2]
        captured["method"] = method
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["headers"] = kwargs.get("headers", {})
        body = b'{"next":"https://maps.worldmonitor.app/tiles"}'
        return _FakeResponse(
            status_code=201,
            body=body,
            content_type="application/json; charset=utf-8",
            url=url,
            headers={
                "content-type": "application/json; charset=utf-8",
                "x-frame-options": "DENY",
                "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
                "cross-origin-opener-policy": "same-origin",
            },
        )

    monkeypatch.setattr(module_routes.requests, "request", fake_request)
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    response = client.post(
        "/world-intelligence/upstream/api/v1/feed?region=eu&region=black-sea",
        content=b'{"scope":"live"}',
        headers={
            "origin": "https://app.abraxas-s3m.com",
            "content-type": "application/json",
            "accept": "application/json",
        },
    )

    assert response.status_code == 201
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.worldmonitor.app/v1/feed?region=eu&region=black-sea"
    assert captured["data"] == b'{"scope":"live"}'
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["headers"]["accept"] == "application/json"
    assert response.headers["content-type"].startswith("application/json")
    assert "x-frame-options" not in response.headers
    assert "frame-ancestors" not in response.headers.get("content-security-policy", "")
    assert "cross-origin-opener-policy" not in response.headers
    assert response.headers["access-control-allow-origin"] == "https://app.abraxas-s3m.com"
    assert response.json()["next"] == "/world-intelligence/upstream/maps/tiles"


def test_world_intelligence_upstream_proxy_handles_options() -> None:
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    response = client.options(
        "/world-intelligence/upstream/clerk/v1/client",
        headers={
            "origin": "https://app.abraxas-s3m.com",
            "access-control-request-headers": "content-type, x-requested-with",
        },
    )

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://app.abraxas-s3m.com"
    assert response.headers["access-control-allow-methods"] == "GET, POST, OPTIONS"


def test_world_intelligence_source_includes_runtime_selection(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(module_routes._runtime_manager, "local_runtime_url", "http://172.17.0.1:8095")
    monkeypatch.setattr(module_routes._runtime_manager, "systemd_control_available", lambda: False)
    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=True,
            training_safe=False,
        ),
    )
    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)

    response = client.get("/api/world-intelligence/source")

    assert response.status_code == 200
    body = response.json()
    assert body["active_source"] == WorldIntelligenceSource.LOCAL_SELF_HOSTED.value
    assert body["local_runtime_healthy"] is True
    assert body["fallback_available"] is True
    assert body["configured_local_url"] == "http://172.17.0.1:8095"
    assert body["systemd_control_available"] is False
    assert body["runtime_url_selected"] == "http://172.17.0.1:8095"


def test_set_local_mode_starts_runtime_and_uses_local_source(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    captured_mode: dict[str, WorldIntelligenceMode] = {}

    def fake_set_mode(mode: WorldIntelligenceMode):
        captured_mode["mode"] = mode
        return None

    monkeypatch.setattr(module_routes._runtime_manager, "set_mode", fake_set_mode)
    monkeypatch.setattr(
        module_routes._runtime_manager,
        "start_local_runtime",
        lambda: (
            ServiceActionResult(
                ok=True,
                action="start",
                service="s3m-world-intelligence",
                detail="ok",
            ),
            LocalRuntimeHealth(
                healthy=True,
                status="healthy",
                endpoint="http://172.17.0.1:8095/health",
                status_code=200,
                detail="local runtime responded",
            ),
        ),
    )
    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=True,
            training_safe=False,
        ),
    )

    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)
    response = client.post("/api/world-intelligence/mode/local")
    assert response.status_code == 200
    assert captured_mode["mode"] == WorldIntelligenceMode.LOCAL_SELF_HOSTED
    assert response.json()["active_source"] == WorldIntelligenceSource.LOCAL_SELF_HOSTED.value


def test_set_local_mode_uses_healthy_runtime_when_systemctl_unavailable(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(
        module_routes._runtime_manager,
        "local_runtime_url",
        "http://172.17.0.1:8095",
    )
    monkeypatch.setattr(
        module_routes._runtime_manager,
        "systemd_control_available",
        lambda: False,
    )
    monkeypatch.setattr(
        module_routes._runtime_manager,
        "set_mode",
        lambda mode: None,
    )
    monkeypatch.setattr(
        module_routes._runtime_manager,
        "start_local_runtime",
        lambda: (
            ServiceActionResult(
                ok=False,
                action="start",
                service="s3m-world-intelligence",
                detail="systemctl unavailable in API container",
            ),
            LocalRuntimeHealth(
                healthy=True,
                status="healthy",
                endpoint="http://172.17.0.1:8095/health",
                status_code=200,
                detail="local runtime responded",
            ),
        ),
    )
    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
            reason="local runtime healthy",
            local_runtime_healthy=True,
            fallback_available=True,
            training_safe=False,
        ),
    )

    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)
    response = client.post("/api/world-intelligence/mode/local")

    assert response.status_code == 200
    body = response.json()
    assert body["active_source"] == WorldIntelligenceSource.LOCAL_SELF_HOSTED.value
    assert body["configured_local_url"] == "http://172.17.0.1:8095"
    assert body["local_runtime_healthy"] is True
    assert body["systemd_control_available"] is False
    assert "systemd control unavailable" in body["reason"]


def test_set_local_mode_returns_safe_payload_when_local_start_fails(monkeypatch) -> None:
    from src.world_intelligence_control import routes as module_routes

    monkeypatch.setattr(
        module_routes._runtime_manager,
        "set_mode",
        lambda mode: None,
    )
    monkeypatch.setattr(
        module_routes._runtime_manager,
        "start_local_runtime",
        lambda: (
            ServiceActionResult(
                ok=False,
                action="start",
                service="s3m-world-intelligence",
                detail="systemctl start failed",
            ),
            LocalRuntimeHealth(
                healthy=False,
                status="down",
                endpoint="http://172.17.0.1:8095",
                detail="local runtime unreachable",
            ),
        ),
    )
    monkeypatch.setattr(
        module_routes._source_manager,
        "resolve_source",
        lambda client_key="global": SourceDecision(
            mode=WorldIntelligenceMode.LOCAL_SELF_HOSTED,
            source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
            reason="local runtime unavailable, switched to external fallback",
            local_runtime_healthy=False,
            fallback_available=True,
            training_safe=False,
        ),
    )

    app = FastAPI()
    app.include_router(world_intelligence_router)
    client = TestClient(app)
    response = client.post("/api/world-intelligence/mode/local")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["active_source"] == WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK.value
    assert "fallback remains active" in body["reason"]
