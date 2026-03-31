"""Unit tests for system health provider."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.system_health_provider import SystemHealthProvider


def test_get_system_health_has_six_layers() -> None:
    provider = SystemHealthProvider()
    payload = provider.get_system_health()
    assert "layers" in payload
    assert len(payload["layers"]) == 6
    for layer in ["llm_core", "threat_detection", "autonomy", "simulation", "navigation", "dashboard"]:
        assert layer in payload["layers"]


def test_overall_status_enum() -> None:
    provider = SystemHealthProvider()
    payload = provider.get_system_health()
    assert payload["overall_status"] in {"operational", "degraded", "critical"}


def test_jetson_stats_shape() -> None:
    provider = SystemHealthProvider()
    payload = provider.get_jetson_stats()
    assert "gpu_util_pct" in payload
    assert "memory_pct" in payload
    assert "temperature_c" in payload


def test_gps_status_shape() -> None:
    provider = SystemHealthProvider()
    payload = provider.get_gps_status()
    assert "quality" in payload
    assert "mode" in payload


def test_api_health_counts() -> None:
    provider = SystemHealthProvider()
    payload = provider.get_api_health()
    assert "healthy" in payload
    assert "unhealthy" in payload
