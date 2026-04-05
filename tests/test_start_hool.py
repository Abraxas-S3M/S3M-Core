"""Unit tests for HOOL startup script helpers."""

from __future__ import annotations

import sys
import threading
import time
import types
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI

from scripts import start_hool


class _CountingAdapter:
    """Adapter stub that counts health polling reads."""

    def __init__(self) -> None:
        self.read_count = 0

    def read_state(self) -> object:
        self.read_count += 1
        return types.SimpleNamespace(
            position=(1.0, 2.0, 3.0),
            autonomy_mode=types.SimpleNamespace(value="supervised"),
        )


def _runtime_stub(*, adapter: _CountingAdapter | None = None, poll_interval: Any = 0.05) -> Any:
    fleet_rows = [
        {
            "platform_id": "alpha-1",
            "type": "uav",
            "adapter_class": "DummyAdapter",
            "position": (1.0, 2.0, 3.0),
            "health_state": "nominal",
        }
    ]
    adapter_obj = adapter or _CountingAdapter()
    registry = types.SimpleNamespace(
        adapters=lambda: {"alpha-1": adapter_obj},
        fleet_status_summary=lambda: fleet_rows,
    )
    configs = types.SimpleNamespace(safety={"safety": {"health_poll_interval_seconds": poll_interval}})
    return types.SimpleNamespace(platform_registry=registry, configs=configs), adapter_obj


def test_build_hool_app_mounts_routes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/hool/status")
    async def hool_status() -> dict[str, str]:
        return {"status": "ok"}

    api_routes_module = types.ModuleType("services.autonomy.hool_extension.api_routes")
    api_routes_module.router = router
    server_module = types.ModuleType("src.api.server")
    server_module.app = app

    monkeypatch.setitem(sys.modules, "services.autonomy.hool_extension.api_routes", api_routes_module)
    monkeypatch.setitem(sys.modules, "src.api.server", server_module)

    mounted = start_hool.build_hool_app()
    assert mounted is app
    assert [route.path for route in app.routes].count("/hool/status") == 1

    mounted_again = start_hool.build_hool_app()
    assert mounted_again is app
    assert [route.path for route in app.routes].count("/hool/status") == 1


def test_start_health_monitor_polling_loop_reads_registered_adapters() -> None:
    runtime, adapter = _runtime_stub()
    stop_event = threading.Event()

    worker = start_hool.start_health_monitor_polling_loop(
        runtime,
        poll_interval_seconds=0.02,
        stop_event=stop_event,
    )
    time.sleep(0.08)
    stop_event.set()
    worker.join(timeout=1.0)

    assert adapter.read_count > 0


def test_resolve_poll_interval_validates_numeric_and_positive() -> None:
    runtime_good, _ = _runtime_stub(poll_interval="0.25")
    assert start_hool._resolve_poll_interval(runtime_good) == 0.25

    runtime_bad_value, _ = _runtime_stub(poll_interval="not-a-number")
    with pytest.raises(ValueError):
        start_hool._resolve_poll_interval(runtime_bad_value)

    runtime_bad_sign, _ = _runtime_stub(poll_interval=0.0)
    with pytest.raises(ValueError):
        start_hool._resolve_poll_interval(runtime_bad_sign)


def test_print_fleet_status_summary_renders_platform_rows(capsys: pytest.CaptureFixture[str]) -> None:
    runtime, _ = _runtime_stub()
    start_hool.print_fleet_status_summary(runtime)
    out = capsys.readouterr().out
    assert "HOOL Fleet Status Summary" in out
    assert "alpha-1" in out
