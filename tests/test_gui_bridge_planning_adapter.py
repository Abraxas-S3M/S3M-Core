"""Tests for planning workspace adapter behavior."""

from __future__ import annotations

import sys
import types

from src.api.gui_bridge.adapters.planning_adapter import PlanningAdapter


def test_build_coas_maps_battle_planner_comparison(monkeypatch) -> None:
    class _FakeBattlePlanner:
        def plan_with_comparison(self, mission_brief: str, num_coas: int = 3):
            assert mission_brief == "Current operational mission"
            assert num_coas == 3
            return {
                "comparison": {
                    "coa_results": [
                        {
                            "profile": {
                                "coa_id": 1,
                                "name": "Aggressive",
                                "approach": "Rapid armored thrust on main axis",
                                "strengths": ["Tempo", "Shock effect"],
                                "weaknesses": ["Exposure"],
                            },
                            "aar": {"friendly_losses": 2, "outcome": "victory"},
                        },
                        {
                            "profile": {
                                "coa_id": 2,
                                "name": "Stealth",
                                "approach": "Low-signature infiltration",
                                "strengths": ["Surprise"],
                                "weaknesses": ["Limited mass"],
                            },
                            "aar": {"friendly_losses": 4, "outcome": "stalemate"},
                        },
                    ]
                }
            }

    monkeypatch.setitem(
        sys.modules,
        "src.apps.battle_planning.battle_planner",
        types.SimpleNamespace(BattlePlanner=_FakeBattlePlanner),
    )

    adapter = PlanningAdapter()
    coas = adapter._build_coas()

    assert len(coas) == 2
    assert coas[0].id == "COA-1"
    assert coas[0].name == "Aggressive"
    assert coas[0].riskScore == 40
    assert coas[0].successProbability == 1.0
    assert coas[0].selected is True
    assert coas[1].id == "COA-2"
    assert coas[1].riskScore == 80
    assert coas[1].successProbability == 0.5
    assert coas[1].selected is False


def test_build_coas_falls_back_to_default_when_planner_fails(monkeypatch) -> None:
    class _BrokenBattlePlanner:
        def __init__(self) -> None:
            raise RuntimeError("planner unavailable")

    monkeypatch.setitem(
        sys.modules,
        "src.apps.battle_planning.battle_planner",
        types.SimpleNamespace(BattlePlanner=_BrokenBattlePlanner),
    )

    adapter = PlanningAdapter()
    coas = adapter._build_coas()
    assert len(coas) == 3
    assert any(coa.name == "Envelopment" for coa in coas)


def test_get_replan_triggers_returns_engine_output(monkeypatch) -> None:
    class _FakePlanRepairEngine:
        def get_active_triggers(self):
            return [{"trigger": "HIGH_ENTROPY", "severity": "high"}]

    monkeypatch.setitem(
        sys.modules,
        "src.replanning.plan_repair_engine",
        types.SimpleNamespace(PlanRepairEngine=_FakePlanRepairEngine),
    )

    adapter = PlanningAdapter()
    payload = adapter.get_replan_triggers()
    assert payload["triggers"] == [{"trigger": "HIGH_ENTROPY", "severity": "high"}]
    assert "updatedAt" in payload


def test_get_suggestions_supports_process_fallback(monkeypatch) -> None:
    class _FakeQueryRequest:
        def __init__(self, prompt: str, domain):
            self.prompt = prompt
            self.domain = domain

    class _FakeResponse:
        def __init__(self, text: str):
            self.text = text

    class _FakeOrchestrator:
        def process(self, request: _FakeQueryRequest):
            assert "Suggest 3 plan modifications." in request.prompt
            return _FakeResponse("1) Re-route flank unit\n2) Delay breach\n3) Increase ISR cadence")

    monkeypatch.setitem(
        sys.modules,
        "src.llm_core.orchestrator",
        types.SimpleNamespace(Orchestrator=_FakeOrchestrator, QueryRequest=_FakeQueryRequest),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.llm_core.engine_registry",
        types.SimpleNamespace(TaskDomain=types.SimpleNamespace(PLANNING="planning")),
    )

    adapter = PlanningAdapter()
    payload = adapter.get_suggestions(plan_context="Bridge approach under observed fires")
    assert payload["suggestions"].startswith("1) Re-route flank unit")
    assert payload["engine"] == "mixtral"
    assert "updatedAt" in payload
