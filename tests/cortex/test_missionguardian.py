"""MissionGuardian: mission continuity, OT safety and change windows as hard constraints.

Military/tactical context:
A plan that would be the cheapest at 10:00 on a Monday may be forbidden until Friday
night; a national-event freeze may forbid anything irreversible. These tests pin that
the guardian classifies routes correctly, that planners obey it, that its validator
names every broken rule, and that the defense cycle schedules rather than violates.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

pytest.importorskip("ortools")

from range.run_contract_cycle import contract_range, run_contract_cycle  # noqa: E402
from src.cortex.breachpath.optimizer import optimize  # noqa: E402
from src.cortex.cybertwin import build_twin  # noqa: E402
from src.cortex.missionguardian.guardian import MissionGuardian, MissionPolicy  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
RIYADH = ZoneInfo("Asia/Riyadh")
MON_10 = datetime(2026, 11, 16, 10, 0, tzinfo=RIYADH)
MON_23 = datetime(2026, 11, 16, 23, 0, tzinfo=RIYADH)
FREEZE_FRI_23 = datetime(2026, 11, 20, 23, 0, tzinfo=RIYADH)
FRI_27_23 = datetime(2026, 11, 27, 23, 0, tzinfo=RIYADH)


def _guard():
    s = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    twin = build_twin(s["routes"], s["vulnerabilities"], m)
    policy = MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml")
    return MissionGuardian(policy, twin, {h["id"]: h["group"] for h in s["hosts"]}), twin


def _as_changes(plan):
    return [{"route_id": a.route_id, "xiid_action": "expire_route" if a.action == "expire" else "narrow_route",
             "reversible": a.reversible} for a in plan.actions]


def test_route_classification() -> None:
    g, _ = _guard()
    assert g.context["rt-users-dc"].tier == 1 and g.context["rt-users-dc"].protected_by == ["R-NO-AUTO-IDENTITY"]
    assert g.context["rt-cams-nvr"].protected_by == ["R-CCTV-SAFETY"]
    assert g.context["rt-users-erpdb"].tier == 2 and g.context["rt-users-erpdb"].missions == ["M-FINANCE"]
    assert g.context["rt-users-jump-rdp"].tier == 1


@pytest.mark.parametrize("now,expected", [
    (MON_10, set()),
    (MON_23, {("expire", "rt-users-erpdb")}),
    (FREEZE_FRI_23, {("narrow", "rt-users-jump-rdp")}),
    (FRI_27_23, {("expire", "rt-users-erpdb"), ("narrow", "rt-users-jump-rdp")}),
])
def test_planner_obeys_windows_and_freezes(now, expected) -> None:
    g, twin = _guard()
    plan = optimize(twin, threshold=0.30, constraints=g.compile_constraints(now))
    assert {(a.action, a.route_id) for a in plan.actions} == expected
    assert g.validate(_as_changes(plan), now) == []


def test_validator_names_every_broken_rule() -> None:
    g, _ = _guard()
    bad = [{"route_id": "rt-cams-nvr", "xiid_action": "expire_route", "reversible": False},
           {"route_id": "rt-users-dc", "xiid_action": "narrow_route", "reversible": True}]
    ids = {(v.rule_id, v.route_id) for v in g.validate(bad, MON_10)}
    assert {("R-CCTV-SAFETY", "rt-cams-nvr"), ("R-REQUIRED-FLOW", "rt-cams-nvr"),
            ("R-TIER-DISRUPTION", "rt-cams-nvr"), ("R-NO-AUTO-IDENTITY", "rt-users-dc"),
            ("W-TIER-1", "rt-users-dc")} <= ids
    many = [{"route_id": r, "xiid_action": "narrow_route", "reversible": True}
            for r in ["rt-users-erp", "rt-users-hr", "rt-users-file"]]
    assert any(v.rule_id == "R-NATIONAL-EVENT-FREEZE" for v in g.validate(many, FREEZE_FRI_23, require_window=False))


def test_schedule_places_changes_in_their_windows() -> None:
    g, twin = _guard()
    plan = optimize(twin, threshold=0.30)
    sched = g.schedule(_as_changes(plan), MON_10)
    assert sched["status"] == "OPTIMAL" and not sched["unschedulable"]
    assert sched["slots"] == {"rt-users-erpdb": "2026-11-16T22:00", "rt-users-jump-rdp": "2026-11-20T22:00"}


def test_cycle_schedules_instead_of_violating(tmp_path) -> None:
    g, _ = _guard()
    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-mg-sched", exposure_target=0.30,
                                                   mission_guard=g, clock=lambda: MON_10))
        assert report.outcome == "scheduled" and rng.state.writes_applied == 0
        deferred = report.analysis["deferred_plan"]
        assert set(deferred["schedule"]["slots"]) == {c["route_id"] for c in deferred["changes"]}
        assert all(o["mission_violations"] for o in report.options if o["option_id"] in {"OPT-B", "OPT-C"})


def test_cycle_executes_only_what_the_window_allows(tmp_path) -> None:
    g, _ = _guard()
    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-mg-23", exposure_target=0.30,
                                                   mission_guard=g, clock=lambda: MON_23))
        assert report.outcome == "verified" and report.recommended_option == "OPT-D"
        assert {c["route_id"] for c in report.changes} == {"rt-users-erpdb"}
        assert rng.state.writes_applied == 1


def test_window_closing_mid_cycle_stops_execution(tmp_path) -> None:
    g, _ = _guard()
    times = iter([MON_23] + [datetime(2026, 11, 17, 6, 0, tzinfo=RIYADH)] * 50)
    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-mg-late", exposure_target=0.30,
                                                   mission_guard=g, clock=lambda: next(times)))
        assert report.outcome in {"rolled_back", "escalated"}
        assert "mission window closed" in report.verification["failure"]["detail"]
        assert rng.state.writes_applied == 0
