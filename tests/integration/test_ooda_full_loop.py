"""
OODA FULL LOOP: Complete cycle from threat detection through autonomous response.
This is the most important integration test in the S3M system.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module

from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.threat_classifier import ThreatClassifier
from src.threat_detection.threat_manager import ThreatManager


AUTONOMY_BT_AVAILABLE = has_module("src.autonomy.behavior_trees")
NAV_PLANNING_AVAILABLE = has_module("src.navigation.planning")
NAV_SAFETY_AVAILABLE = has_module("src.navigation.safety")
DASHBOARD_AGG_AVAILABLE = has_module("src.dashboard.aggregator")


@pytest.mark.skipif(not (AUTONOMY_BT_AVAILABLE and NAV_PLANNING_AVAILABLE), reason="Full OODA loop requires autonomy behavior trees + navigation planning")
def test_full_ooda_cycle() -> None:
    manager = ThreatManager()
    event = manager.ingest_manual(
        "Enemy UAV detected",
        "Hostile UAV observed at grid 500,300",
        ThreatLevel.HIGH,
        ThreatCategory.KINETIC,
    )

    classifier = ThreatClassifier()
    assessed = classifier.classify(event)
    assert assessed.llm_assessment

    from src.autonomy.behavior_trees.nodes import ConditionNode, EngageNode, PatrolNode, SelectorNode, SequenceNode
    from src.navigation.planning.path_planner import PathPlanner

    tree = SelectorNode(children=[SequenceNode(children=[ConditionNode("threat_close"), EngageNode()]), PatrolNode()])
    context = {
        "agent_position": (100, 100, 50),
        "threats": [{"position": (500, 300, 0), "level": "HIGH"}],
        "nearest_threat_distance": 450,
        "rules_of_engagement": "weapons_free",
        "waypoints": [(200, 200, 50)],
        "current_waypoint_idx": 0,
        "battery_pct": 85,
        "decision_log": [],
    }
    tree.tick(context)
    assert context["decision_log"]

    planner = PathPlanner()
    path = planner.plan((100, 100, 50), (500, 300, 0), obstacles=[{"position": (300, 200, 30), "radius": 25}])
    assert path is not None

    sensor_manager = SensorManager()
    sensor_manager.register_sensor("radar_ooda", SensorType.RADAR)
    for _ in range(4):
        sensor_manager.ingest("radar_ooda", data={"x": 500, "y": 300, "z": 0, "classification": "aircraft"}, position=(500, 300, 0))
    tracks = sensor_manager.process()
    assert tracks

    if DASHBOARD_AGG_AVAILABLE:
        from src.dashboard.aggregator import DashboardAggregator

        overview = DashboardAggregator().get_overview()
        assert isinstance(overview, dict)

    threats = manager.get_threats(limit=10)
    assert any(t.event_id == event.event_id for t in threats)


@pytest.mark.skipif(not (NAV_PLANNING_AVAILABLE and NAV_SAFETY_AVAILABLE), reason="Replan test requires navigation planning + safety layers")
def test_full_cycle_with_replan() -> None:
    from src.navigation.planning.path_planner import PathPlanner
    from src.navigation.safety.collision_checker import CollisionChecker

    planner = PathPlanner()
    initial = planner.plan((0, 0, 0), (100, 100, 50), obstacles=[])

    checker = CollisionChecker()
    collision = checker.check_path(initial, obstacles=[{"position": (50, 50, 25), "radius": 30}])

    if not getattr(collision, "safe", False):
        replanned = planner.plan((0, 0, 0), (100, 100, 50), obstacles=[{"position": (50, 50, 25), "radius": 30}])
        assert replanned is not None
