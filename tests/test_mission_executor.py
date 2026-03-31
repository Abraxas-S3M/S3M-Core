"""Tests for mission executor runtime and decision logging."""

from __future__ import annotations

from src.autonomy.behavior_trees import ActionNode, BTStatus, MissionExecutor, SequenceNode
from src.autonomy.models import AutonomyDecision, MissionStatus


def test_mission_executor_runs_to_completion() -> None:
    tree = SequenceNode(
        "root",
        children=[
            ActionNode("a1", lambda ctx: BTStatus.SUCCESS),
            ActionNode("a2", lambda ctx: BTStatus.SUCCESS),
        ],
    )
    executor = MissionExecutor(tree=tree, tick_rate_hz=100.0)
    status = executor.run(context={"decision_log": []}, max_ticks=10)
    assert status == MissionStatus.COMPLETED


def test_tick_count_and_decision_logging() -> None:
    tree = ActionNode("single", lambda ctx: BTStatus.SUCCESS)
    context = {"decision_log": []}
    executor = MissionExecutor(tree=tree, tick_rate_hz=100.0)
    result = executor.run(context=context, max_ticks=5)
    assert result == MissionStatus.COMPLETED
    state = executor.get_status()
    assert state["ticks_executed"] >= 1
    assert isinstance(executor.get_decision_log(), list)


def test_abort_stops_execution() -> None:
    tree = ActionNode("run", lambda ctx: BTStatus.RUNNING)
    executor = MissionExecutor(tree=tree, tick_rate_hz=100.0)
    executor.start({"decision_log": []})
    executor.abort()
    assert executor.get_status()["aborted"] is True


def test_get_decision_log_returns_autonomy_decisions() -> None:
    tree = ActionNode("run", lambda ctx: BTStatus.SUCCESS)
    decision = AutonomyDecision(
        decision_id="d-1",
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        decision_type=__import__("src.autonomy.models", fromlist=["DecisionType"]).DecisionType.HOLD,
        agent_id="a1",
        mission_id=None,
        context={},
        action_taken={},
        alternatives_considered=[],
        confidence=0.9,
        reasoning="test",
        llm_consulted=False,
        requires_human_review=False,
        risk_score=0.1,
    )
    context = {"decision_log": [decision]}
    executor = MissionExecutor(tree=tree, tick_rate_hz=100.0)
    executor.start(context)
    _ = executor.tick()
    decisions = executor.get_decision_log()
    assert all(isinstance(d, AutonomyDecision) for d in decisions)
