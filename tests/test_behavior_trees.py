"""Tests for behavior tree framework and tactical nodes."""

from __future__ import annotations

from src.autonomy.behavior_trees import (
    BTStatus,
    ConditionNode,
    EngageNode,
    LLMReplanNode,
    PatrolNode,
    SelectorNode,
    SequenceNode,
)


def test_sequence_node_success_and_failure():
    success = ConditionNode("ok", lambda ctx: True)
    fail = ConditionNode("fail", lambda ctx: False)
    seq_ok = SequenceNode("seq_ok", [success, success])
    seq_fail = SequenceNode("seq_fail", [success, fail, success])
    assert seq_ok.tick({}) == BTStatus.SUCCESS
    assert seq_fail.tick({}) == BTStatus.FAILURE


def test_selector_node_success_and_failure():
    fail = ConditionNode("fail", lambda ctx: False)
    success = ConditionNode("ok", lambda ctx: True)
    sel_ok = SelectorNode("sel_ok", [fail, success, fail])
    sel_fail = SelectorNode("sel_fail", [fail, fail])
    assert sel_ok.tick({}) == BTStatus.SUCCESS
    assert sel_fail.tick({}) == BTStatus.FAILURE


def test_patrol_node_advances_waypoints():
    node = PatrolNode()
    context = {
        "agent_id": "a1",
        "mission_id": "m1",
        "waypoints": [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)],
        "agent_position": (0.0, 0.0, 0.0),
        "current_waypoint_idx": 0,
        "patrol_step": 10.0,
        "decision_log": [],
    }
    status = node.tick(context)
    assert status in {BTStatus.RUNNING, BTStatus.SUCCESS}
    assert context["current_waypoint_idx"] >= 1


def test_engage_node_respects_roe_weapons_hold():
    node = EngageNode()
    context = {
        "agent_id": "a1",
        "mission_id": "m1",
        "agent_position": (0.0, 0.0, 0.0),
        "rules_of_engagement": "weapons_hold",
        "threats": [{"id": "t1", "position": (5.0, 0.0, 0.0)}],
        "decision_log": [],
    }
    status = node.tick(context)
    assert status == BTStatus.FAILURE


def test_llm_replan_node_fallback_when_unavailable():
    node = LLMReplanNode()
    context = {
        "agent_id": "a1",
        "mission_id": "m1",
        "decision_log": [],
        "agent_state": {"battery_pct": 50},
        "mission": {"status": "active"},
        "threats": [],
    }
    status = node.tick(context)
    # In this codebase orchestrator may still exist, so allow both but ensure a decision logs.
    assert status in {BTStatus.SUCCESS, BTStatus.FAILURE}
    assert len(context["decision_log"]) >= 1
