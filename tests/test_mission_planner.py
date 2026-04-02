"""Tests for multi-domain mission planning optimization and fallbacks."""

from __future__ import annotations

import sys
import types

import pytest

from src.planning.mission_planner import (
    Asset,
    MissionDomain,
    MissionTask,
    MultiDomainMissionPlanner,
    ORToolsPlanner,
    TaskPriority,
)


def _asset(
    asset_id: str,
    domains: list[MissionDomain],
    endurance_hours: float = 2.0,
    readiness_score: float = 0.9,
) -> Asset:
    return Asset(
        asset_id=asset_id,
        callsign=f"CS-{asset_id}",
        domains=domains,
        readiness_score=readiness_score,
        endurance_hours=endurance_hours,
        speed_kmh=120.0,
        lat=24.0,
        lon=54.0,
    )


def _task(
    task_id: str,
    priority: TaskPriority,
    required_assets: int,
    duration_hours: float = 2.0,
) -> MissionTask:
    return MissionTask(
        task_id=task_id,
        description_en=f"Task {task_id}",
        description_ar=f"مهمة {task_id}",
        domain=MissionDomain.AIR,
        priority=priority,
        required_assets=required_assets,
        duration_hours=duration_hours,
        lat=24.0,
        lon=54.0,
        time_window_start=0,
        time_window_end=12,
    )


def test_greedy_fallback_prioritizes_critical_full_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.planning.mission_planner.ORTOOLS_AVAILABLE", False)

    planner = ORToolsPlanner()
    assets = [_asset("a1", [MissionDomain.AIR]), _asset("a2", [MissionDomain.AIR])]
    tasks = [
        _task("critical", TaskPriority.CRITICAL, required_assets=2),
        _task("high", TaskPriority.HIGH, required_assets=1),
    ]

    assignments, unassigned = planner.plan(tasks, assets)
    assert [a.task_id for a in assignments] == ["critical"]
    assert unassigned == ["high"]


def test_greedy_fallback_rejects_partial_required_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.planning.mission_planner.ORTOOLS_AVAILABLE", False)

    planner = ORToolsPlanner()
    assets = [_asset("a1", [MissionDomain.AIR])]
    tasks = [_task("needs-two", TaskPriority.CRITICAL, required_assets=2)]
    assignments, unassigned = planner.plan(tasks, assets)

    assert assignments == []
    assert unassigned == ["needs-two"]


def test_cp_sat_prefers_higher_priority_task_when_available() -> None:
    mp = pytest.importorskip("src.planning.mission_planner")
    if not mp.ORTOOLS_AVAILABLE:
        pytest.skip("or-tools unavailable")

    planner = ORToolsPlanner()
    assets = [_asset("a1", [MissionDomain.AIR]), _asset("a2", [MissionDomain.AIR])]
    tasks = [
        _task("critical", TaskPriority.CRITICAL, required_assets=2),
        _task("high", TaskPriority.HIGH, required_assets=1),
    ]

    assignments, unassigned = planner.plan(tasks, assets)
    assigned_ids = {a.task_id for a in assignments}
    # Tactical context: in constrained force-allocation, solver should commit
    # scarce platforms to the highest-priority executable mission first.
    assert "critical" in assigned_ids
    assert "high" in unassigned


def test_generate_plan_without_llm_sets_coverage_and_none_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.planning.mission_planner.ORTOOLS_AVAILABLE", False)

    planner = MultiDomainMissionPlanner(use_llm=False)
    assets = [_asset("a1", [MissionDomain.AIR]), _asset("a2", [MissionDomain.AIR])]
    tasks = [
        _task("t1", TaskPriority.CRITICAL, required_assets=1),
        _task("t2", TaskPriority.HIGH, required_assets=3),
    ]

    plan = planner.generate_plan(tasks, assets)
    assert plan.coverage_pct == 50.0
    assert plan.llm_assessment is None
    payload = plan.to_dict()
    assert payload["assignments"][0]["domain"] == "AIR"
    assert payload["assignments"][0]["priority"] == 1


def test_llm_red_team_uses_orchestrator_and_stringifies_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = types.ModuleType("src.llm_core.orchestrator")

    class _FakeOrchestrator:
        def route_and_decide(self, _: str):
            return {"assessment": "ok"}

    setattr(fake_module, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setitem(sys.modules, "src.llm_core.orchestrator", fake_module)

    planner = MultiDomainMissionPlanner(use_llm=True)
    out = planner._llm_red_team(assignments=[], unassigned=["t9"])
    assert isinstance(out, str)
    assert "assessment" in out

