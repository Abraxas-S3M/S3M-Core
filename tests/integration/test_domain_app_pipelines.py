"""
Tests that each Phase 11 domain application pipeline works end-to-end.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module


APPS_AVAILABLE = has_module("src.apps")


@pytest.mark.skipif(not APPS_AVAILABLE, reason="Domain apps layer not available in this repository snapshot")
def test_battle_planning_pipeline() -> None:
    from src.apps.battle_planning import BattlePlanner

    planner = BattlePlanner()
    out = planner.plan("Conduct a 4-UAV patrol of sector Alpha")
    assert isinstance(out, dict)
    assert "opord" in out and "scenario" in out and "aar" in out


@pytest.mark.skipif(not APPS_AVAILABLE, reason="Domain apps layer not available in this repository snapshot")
def test_logistics_pipeline() -> None:
    from src.apps.logistics import LogisticsModule

    module = LogisticsModule()
    for idx in range(5):
        module.add_inventory_item(f"item-{idx}", quantity=100)
    module.deplete("item-0", 95)
    module.deplete("item-1", 95)
    restock = module.check_inventory()
    assert len(restock) >= 2


@pytest.mark.skipif(not APPS_AVAILABLE, reason="Domain apps layer not available in this repository snapshot")
def test_threat_hunting_pipeline() -> None:
    from src.apps.threat_hunting import ThreatHuntingModule

    module = ThreatHuntingModule()
    events = [{"source_ip": "10.0.0.77", "category": "CYBER", "timestamp": f"2026-01-01T00:00:{i:02d}Z"} for i in range(5)]
    out = module.hunt(events)
    assert out is not None


@pytest.mark.skipif(not APPS_AVAILABLE, reason="Domain apps layer not available in this repository snapshot")
def test_geopolitical_pipeline() -> None:
    from src.apps.geopolitical import GeopoliticalModule

    module = GeopoliticalModule()
    out = module.analyze_event("Naval confrontation reported in the Strait of Hormuz", "Persian Gulf")
    assert isinstance(out, dict)


@pytest.mark.skipif(not APPS_AVAILABLE, reason="Domain apps layer not available in this repository snapshot")
def test_drone_ops_pipeline() -> None:
    from src.apps.drone_ops import DroneOpsModule

    module = DroneOpsModule()
    mission = module.plan_mission("PATROL", [(0, 0, 50), (100, 100, 50), (200, 150, 50)])
    assert isinstance(mission, dict)
