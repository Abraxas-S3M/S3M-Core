"""Unit tests for Layer 06 LLM monitor provider."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.llm_monitor_provider import LLMMonitorProvider


def test_engine_status_returns_four_items() -> None:
    provider = LLMMonitorProvider()
    engines = provider.get_engine_status()
    assert isinstance(engines, list)
    assert len(engines) == 4


def test_metrics_has_expected_keys() -> None:
    provider = LLMMonitorProvider()
    metrics = provider.get_metrics()
    for key in [
        "total_requests",
        "uptime_seconds",
        "engines_loaded",
        "avg_latency_ms",
        "requests_per_minute",
    ]:
        assert key in metrics


def test_audit_log_returns_list() -> None:
    provider = LLMMonitorProvider()
    entries = provider.get_audit_log(limit=5)
    assert isinstance(entries, list)


def test_routing_returns_dict() -> None:
    provider = LLMMonitorProvider()
    routing = provider.get_routing()
    assert isinstance(routing, dict)
    assert len(routing) >= 1
