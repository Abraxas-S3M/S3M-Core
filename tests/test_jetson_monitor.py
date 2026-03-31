"""Unit tests for Jetson monitor telemetry and fallback behavior."""

from __future__ import annotations

from src.navigation.edge_inference.jetson_monitor import JetsonMonitor
from src.navigation.models import JetsonStats


def test_get_stats_returns_jetson_stats() -> None:
    monitor = JetsonMonitor()
    stats = monitor.get_stats()
    assert isinstance(stats, JetsonStats)


def test_is_thermal_throttling_with_simulated_data() -> None:
    monitor = JetsonMonitor()
    _ = monitor.get_stats()
    assert isinstance(monitor.is_thermal_throttling(), bool)


def test_get_cuda_info_reports_availability() -> None:
    monitor = JetsonMonitor()
    info = monitor.get_cuda_info()
    assert "tensorrt_available" in info
    assert "onnxruntime_available" in info


def test_recommend_model_budget_positive() -> None:
    monitor = JetsonMonitor()
    budget = monitor.recommend_model_budget()
    assert budget > 0.0


def test_memory_pressure_range() -> None:
    monitor = JetsonMonitor()
    pressure = monitor.get_stats().memory_pressure()
    assert 0.0 <= pressure <= 1.0
