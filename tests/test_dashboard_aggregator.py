"""Unit tests for Layer 06 dashboard aggregator."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.aggregator import DashboardAggregator
from src.dashboard.providers.runtime_store import reset_runtime_state


def setup_function() -> None:
    reset_runtime_state()


def test_dashboard_aggregator_initialization() -> None:
    agg = DashboardAggregator()
    assert agg.cop_provider is not None
    assert agg.llm_provider is not None
    assert agg.threat_provider is not None
    assert agg.autonomy_provider is not None
    assert agg.system_provider is not None
    assert agg.alert_manager is not None


def test_overview_has_expected_keys() -> None:
    agg = DashboardAggregator()
    data = agg.get_overview()
    assert isinstance(data, dict)
    assert "llm" in data
    assert "threats" in data
    assert "autonomy" in data
    assert "simulation" in data
    assert "navigation" in data
    assert "system" in data


def test_overview_safe_defaults_when_layers_unavailable() -> None:
    agg = DashboardAggregator()
    data = agg.get_overview()
    assert data["llm"]["engines_loaded"] >= 0
    assert data["threats"]["total_events"] >= 0
    assert data["autonomy"]["total_agents"] >= 0
    assert data["system"]["gpu_util_pct"] >= 0


def test_health_check_reports_provider_statuses() -> None:
    agg = DashboardAggregator()
    health = agg.health_check()
    assert isinstance(health, dict)
    assert "providers" in health
    for provider in ["cop", "llm", "threats", "autonomy", "system", "alerts"]:
        assert provider in health["providers"]
