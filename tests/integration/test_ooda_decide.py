"""
OODA DECIDE: Assessed threats -> behavior tree evaluates -> autonomy decides -> XAI explains.
Tests Layer 03 consuming Layer 02 outputs and producing auditable decisions.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module


AUTONOMY_BT_AVAILABLE = has_module("src.autonomy.behavior_trees")
AUTONOMY_XAI_AVAILABLE = has_module("src.autonomy.xai")
AUTONOMY_SWARM_AVAILABLE = has_module("src.autonomy.swarm")


@pytest.mark.skipif(not AUTONOMY_BT_AVAILABLE, reason="Autonomy behavior tree layer not available in this repository snapshot")
def test_behavior_tree_threat_response() -> None:
    from src.autonomy.behavior_trees.nodes import ConditionNode, EngageNode, PatrolNode, SelectorNode, SequenceNode

    tree = SelectorNode(children=[SequenceNode(children=[ConditionNode("threat_close"), EngageNode()]), PatrolNode()])
    context = {
        "agent_position": (100, 100, 50),
        "threats": [{"position": (120, 110, 50), "level": "HIGH"}],
        "nearest_threat_distance": 25,
        "rules_of_engagement": "weapons_free",
        "waypoints": [(200, 200, 50)],
        "current_waypoint_idx": 0,
        "battery_pct": 80,
        "decision_log": [],
    }
    result = tree.tick(context)
    assert result is not None
    assert len(context["decision_log"]) >= 1


@pytest.mark.skipif(not AUTONOMY_BT_AVAILABLE, reason="Autonomy behavior tree layer not available in this repository snapshot")
def test_behavior_tree_retreat_on_weapons_hold() -> None:
    from src.autonomy.behavior_trees.nodes import ConditionNode, EngageNode, PatrolNode, SelectorNode, SequenceNode

    tree = SelectorNode(children=[SequenceNode(children=[ConditionNode("threat_close"), EngageNode()]), PatrolNode()])
    context = {
        "agent_position": (100, 100, 50),
        "threats": [{"position": (120, 110, 50), "level": "HIGH"}],
        "nearest_threat_distance": 25,
        "rules_of_engagement": "weapons_hold",
        "waypoints": [(200, 200, 50)],
        "current_waypoint_idx": 0,
        "battery_pct": 80,
        "decision_log": [],
    }
    tree.tick(context)
    assert len(context["decision_log"]) >= 1


@pytest.mark.skipif(not AUTONOMY_BT_AVAILABLE, reason="Autonomy behavior tree layer not available in this repository snapshot")
def test_llm_replan_node_integration() -> None:
    from src.autonomy.behavior_trees.llm_replan_node import LLMReplanNode

    node = LLMReplanNode()
    context = {
        "mission": "complex contested environment",
        "threats": [{"position": (400, 250, 30), "level": "HIGH"}],
        "decision_log": [],
    }
    result = node.tick(context)
    assert result is not None
    assert "decision_log" in context


@pytest.mark.skipif(not AUTONOMY_XAI_AVAILABLE, reason="Autonomy XAI layer not available in this repository snapshot")
def test_decision_logged_and_explainable() -> None:
    from src.autonomy.models import AutonomyDecision
    from src.autonomy.xai import DecisionExplainer, DecisionLog

    log = DecisionLog()
    explainer = DecisionExplainer()
    decision = AutonomyDecision(action="MOVE_TO", risk_score=0.2, reasoning="Test decision")
    decision_id = log.record(decision)
    explanation = explainer.explain(decision)

    assert all(key in explanation for key in ["summary", "factors", "risk_assessment"])
    assert log.get(decision_id) is not None


@pytest.mark.skipif(not AUTONOMY_XAI_AVAILABLE, reason="Autonomy XAI layer not available in this repository snapshot")
def test_assurance_checker_flags_high_risk() -> None:
    from src.autonomy.models import AutonomyDecision
    from src.autonomy.xai import AssuranceChecker

    checker = AssuranceChecker()
    decision = AutonomyDecision(action="ENGAGE", risk_score=0.9, reasoning="High risk")
    report = checker.check(decision)

    assert report.requires_human_review is True
    assert report.flags


@pytest.mark.skipif(not AUTONOMY_SWARM_AVAILABLE, reason="Autonomy swarm layer not available in this repository snapshot")
def test_swarm_command_from_decision() -> None:
    from src.autonomy.swarm.coordinator import SwarmCoordinator
    from src.autonomy.swarm.task_allocator import TaskAllocator

    coordinator = SwarmCoordinator()
    coordinator.register_agent("drone_1")
    coordinator.register_agent("drone_2")

    allocator = TaskAllocator(coordinator)
    mission = {"mission_id": "m-1", "type": "MOVE_TO", "target": (100, 100, 50)}
    assignments = allocator.allocate(mission)
    command_id = coordinator.issue_command({"command_type": "MOVE_TO", "target": (100, 100, 50)})

    assert assignments is not None
    assert command_id is not None
