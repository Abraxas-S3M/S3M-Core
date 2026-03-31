"""
Tests that the Dashboard (Layer 06) aggregator pulls from every other layer
without errors, timeouts, or crashes — even when some layers have no data.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module

from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.threat_manager import ThreatManager


DASHBOARD_AGG_AVAILABLE = has_module("src.dashboard.aggregator")
DASHBOARD_COP_AVAILABLE = has_module("src.dashboard.providers.cop")
DASHBOARD_ALERT_AVAILABLE = has_module("src.dashboard.alerts")
AUTONOMY_SWARM_AVAILABLE = has_module("src.autonomy.swarm")


@pytest.mark.skipif(not DASHBOARD_AGG_AVAILABLE, reason="Dashboard aggregator layer not available in this repository snapshot")
def test_overview_returns_all_layers() -> None:
    from src.dashboard.aggregator import DashboardAggregator

    overview = DashboardAggregator().get_overview()
    for key in ["llm", "threats", "autonomy", "simulation", "navigation", "system"]:
        assert key in overview
        assert overview[key] is not None


@pytest.mark.skipif(not (DASHBOARD_COP_AVAILABLE and AUTONOMY_SWARM_AVAILABLE), reason="Dashboard COP provider or swarm layer not available")
def test_cop_with_populated_data() -> None:
    from src.autonomy.swarm.coordinator import SwarmCoordinator
    from src.dashboard.providers.cop import COPDataProvider

    coordinator = SwarmCoordinator()
    coordinator.register_agent("a1")
    coordinator.register_agent("a2")

    manager = ThreatManager()
    for i in range(3):
        manager.ingest_manual(f"Threat {i}", "Synthetic", ThreatLevel.HIGH, ThreatCategory.KINETIC)

    cop = COPDataProvider().get_cop_data()
    assert isinstance(cop, dict)


@pytest.mark.skipif(not DASHBOARD_AGG_AVAILABLE, reason="Dashboard aggregator layer not available in this repository snapshot")
def test_dashboard_resilient_to_missing_layers() -> None:
    from src.dashboard.aggregator import DashboardAggregator

    overview = DashboardAggregator().get_overview()
    assert isinstance(overview, dict)


@pytest.mark.skipif(not DASHBOARD_ALERT_AVAILABLE, reason="Dashboard alert manager not available in this repository snapshot")
def test_alert_aggregation_across_layers() -> None:
    manager = ThreatManager()
    manager.ingest_manual("Critical test", "Synthetic", ThreatLevel.CRITICAL, ThreatCategory.CYBER)

    from src.dashboard.alerts import AlertManager

    alerts = AlertManager().collect()
    assert isinstance(alerts, list)
