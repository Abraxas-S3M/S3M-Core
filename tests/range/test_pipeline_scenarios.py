"""Scenario acceptance tests for the synthetic cyber range pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from range.pipeline import CortexRangePipeline, load_scenario

SCENARIOS = Path(__file__).resolve().parents[2] / "range" / "scenarios"


@pytest.fixture
def pipeline(tmp_path: Path) -> CortexRangePipeline:
    return CortexRangePipeline(work_dir=tmp_path / "staging")


def test_scenario_a_zero_writes_and_injection_alert(pipeline: CortexRangePipeline) -> None:
    scenario = load_scenario(SCENARIOS / "scenario_a_poisoned_log.yaml")
    state = pipeline.run_scenario(scenario)
    assert state.writes_executed == 0
    alert_types = {a.alert_type for a in state.alerts}
    assert "prompt_injection" in alert_types
    assert state.stages.get("evidence_verified") is True


def test_scenario_b_approval_containment(pipeline: CortexRangePipeline) -> None:
    scenario = load_scenario(SCENARIOS / "scenario_b_cctv_shield.yaml")
    state = pipeline.run_scenario(scenario, approver_override="approve")
    assert state.change_applied is True
    assert state.predicted_matches_observed is True
    assert state.protected_route_touched is False
    assert state.required_flows_reachable is True


def test_scenario_b_duress_denied_with_alert(pipeline: CortexRangePipeline) -> None:
    scenario = load_scenario(SCENARIOS / "scenario_b_cctv_shield.yaml")
    state = pipeline.run_scenario(scenario, approver_override="duress")
    assert state.change_applied is False
    assert any(a.alert_type == "duress_approval" for a in state.alerts)


def test_scenario_c_broker_refuses_after_switch(pipeline: CortexRangePipeline) -> None:
    scenario = load_scenario(SCENARIOS / "scenario_c_rug_pull.yaml")
    state = pipeline.run_scenario(scenario)
    assert state.broker_refused is True
    alert_types = {a.alert_type for a in state.alerts}
    assert "tool_description_rug_pull" in alert_types
