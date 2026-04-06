"""Unit tests for deployment-aware API startup script."""

from __future__ import annotations

import sys
import types

import pytest

from scripts import start_api


def test_preflight_cloud_check_warns_on_insecure_settings() -> None:
    config = types.SimpleNamespace(
        cors_origins=["*"],
        auth_enabled=True,
        api_key=None,
        device="cuda",
    )

    warnings = start_api._preflight_cloud_check(config)

    assert "CORS_ORIGINS is wildcard or empty — set explicitly for production" in warnings
    assert "S3M_AUTH_ENABLED=true but no S3M_API_KEY set" in warnings
    assert "Cloud demo should use CPU but device=cuda" in warnings


def test_preflight_cloud_check_passes_hardened_settings() -> None:
    config = types.SimpleNamespace(
        cors_origins=["https://ops.s3m.local"],
        auth_enabled=True,
        api_key="test-key",
        device="cpu",
    )

    warnings = start_api._preflight_cloud_check(config)

    assert warnings == []


def test_main_reads_deployment_mode_env_and_starts_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api_config = types.SimpleNamespace(
        host="0.0.0.0",
        port=8080,
        workers=1,
        log_level="info",
        device="cpu",
        auth_enabled=True,
        api_key="test-key",
        cors_origins=["https://ops.s3m.local"],
        deployment_mode="jetson_edge",
    )
    config_module = types.ModuleType("src.api.config")
    config_module.api_config = api_config
    monkeypatch.setitem(sys.modules, "src.api.config", config_module)

    call_record: dict[str, object] = {}

    def fake_uvicorn_run(*args: object, **kwargs: object) -> None:
        call_record["args"] = args
        call_record["kwargs"] = kwargs

    uvicorn_module = types.ModuleType("uvicorn")
    uvicorn_module.run = fake_uvicorn_run
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)

    monkeypatch.setenv("DEPLOYMENT_MODE", "cloud_cpu_demo")
    start_api.main()

    output = capsys.readouterr().out
    assert "Mode: CLOUD CPU DEMO" in output
    assert "Deployment Mode: cloud_cpu_demo" in output
    assert "Device: CPU" in output
    assert "Auth: ENABLED" in output
    assert "CORS: https://ops.s3m.local" in output
    assert "[WARN]" not in output

    assert call_record["args"] == ("src.api.server:app",)
    assert call_record["kwargs"] == {
        "host": "0.0.0.0",
        "port": 8080,
        "workers": 1,
        "log_level": "info",
        "reload": False,
    }
