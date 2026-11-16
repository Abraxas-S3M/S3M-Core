"""AutoHeal: detect, localise, restore approved state, verify - or escalate.

Military/tactical context:
Self-repair must restore what was approved and nothing else, must find faults that every
component hides, must refuse to touch protected infrastructure, and must never claim
success without fresh evidence. Each test injects one fault into the reference control
plane and checks the incident outcome.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

pytest.importorskip("ortools")

from range.run_contract_cycle import contract_range, make_cycle  # noqa: E402
from src.cortex.autoheal import fsm as fsm_mod  # noqa: E402
from src.cortex.autoheal.healer import AutoHeal, snapshot_baseline  # noqa: E402
from src.cortex.cybertwin import build_twin  # noqa: E402
from src.cortex.missionguardian.guardian import MissionGuardian, MissionPolicy  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
WORKDAY = datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Riyadh"))


def _guard():
    s = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    twin = build_twin(s["routes"], s["vulnerabilities"], m)
    return MissionGuardian(MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml"), twin,
                           {h["id"]: h["group"] for h in s["hosts"]})


def _heal(rng, tmp_path, name, *, before=None, inject=None, policy=None):
    """Snapshot approved baseline (after ``before``), inject a fault, run one incident."""
    if before:
        for f in before:
            rng.admin(f)
    base_routes, base_stlinks = snapshot_baseline(rng.state.model.list_routes(), rng.state.model.list_stlinks())
    for f in inject or []:
        rng.admin(f)
    cycle, transport = make_cycle(rng, workdir=tmp_path, case_id=name, sandbox="sbx-range-full",
                                  board_policy=policy, mission_guard=_guard(), clock=lambda: WORKDAY)
    healer = AutoHeal(cycle=cycle, baseline_routes=base_routes, baseline_stlinks=base_stlinks)

    async def go():
        try:
            return await healer.run(name)
        finally:
            await transport.close()

    return asyncio.run(go())


@pytest.fixture
def rng():
    with contract_range() as r:
        yield r


def test_state_machine_is_safe_and_live() -> None:
    result = fsm_mod.check_model()
    assert result["ok"] and result["complete_paths"] == 8


def test_model_check_catches_a_broken_table(monkeypatch) -> None:
    bad = dict(fsm_mod.TRANSITIONS)
    bad[("PLANNED", "shortcut")] = "REPAIRING"  # skip authorisation
    monkeypatch.setattr(fsm_mod, "TRANSITIONS", bad)
    monkeypatch.setattr(fsm_mod, "EVENTS", sorted({e for _, e in bad}))
    assert any("REPAIRING without AUTHORIZED" in v for v in fsm_mod.check_model()["violations"])


def test_runtime_rejects_illegal_transition() -> None:
    m = fsm_mod.IncidentFSM("x")
    with pytest.raises(fsm_mod.IllegalTransition):
        m.fire("repair_started")


def test_healthy_fabric_closes_without_action(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-none")
    assert rep.state == "CLOSED_NO_FAULT" and rng.state.writes_applied == 0
    assert sum(p["verdict"] == "healthy" for p in rep.probes) >= 10


def test_route_drift_restored(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-drift", inject=[{"mode": "route_drift", "route_id": "rt-users-erp", "status": "expired"}])
    assert rep.state == "RESOLVED"
    assert [(r["action"], r["state"]) for r in rep.repairs] == [("restore_route", "applied")]
    assert rng.state.model.find_route("rt-users-erp")["status"] == "active"
    assert {f["kind"] for f in rep.faults} == {"route_drift"}


def test_unauthorized_reactivation_re_expired(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-unauth",
                before=[{"mode": "route_drift", "route_id": "rt-mail-file", "status": "expired"}],
                inject=[{"mode": "route_drift", "route_id": "rt-mail-file", "status": "active"}])
    assert rep.state == "RESOLVED" and rep.faults[0]["kind"] == "unauthorized_route"
    assert rep.repairs[0]["action"] == "expire_route"
    assert rep.exposure["within_baseline"]


def test_stlink_down_reenabled_with_two_approvals(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-down", inject=[{"mode": "stlink_down", "stlink_id": "stlink-srv-hr-db-01"}])
    assert rep.state == "RESOLVED"
    assert rep.repairs[0]["action"] == "enable_stlink" and rep.repairs[0]["approvals"] >= 2


def test_silent_failure_localised_to_shared_stlink(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-silent", inject=[{"mode": "silent_stlink", "host": "srv-nvr-01"}])
    failed = {p["flow_id"] for p in rep.probes if p["verdict"] == "failed"}
    assert failed == {"F-CCTV-INGEST", "F-CCTV-VMS"}
    assert [f["component"] for f in rep.faults] == ["stlink:stlink-srv-nvr-01"]
    assert rep.state == "RESOLVED" and rep.repairs[0]["action"] == "deploy_stlink"
    assert all(p["verdict"] != "failed" for p in rep.probes_after)


def test_protected_route_escalates_without_writes(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-dc", inject=[{"mode": "route_drift", "route_id": "rt-users-dc", "status": "expired"}])
    assert rep.state == "ESCALATED" and rng.state.writes_applied == 0
    assert rep.escalations[0]["rules"] == ["R-NO-AUTO-IDENTITY"]


def test_repair_that_does_not_take_effect_escalates(rng, tmp_path) -> None:
    rng.state.drop_next_write = True  # control plane acknowledges the redeploy but does nothing
    rep = _heal(rng, tmp_path, "ah-noeffect", inject=[{"mode": "silent_stlink", "host": "srv-nvr-01"}])
    assert rep.state == "ESCALATED"
    assert "VERIFYING" in [h["to"] for h in rep.history]  # the receipt passed; fresh probes did not


def test_denied_repair_escalates(rng, tmp_path) -> None:
    rep = _heal(rng, tmp_path, "ah-deny", inject=[{"mode": "route_drift", "route_id": "rt-users-erp", "status": "expired"}],
                policy=lambda payload: "DENY")
    assert rep.state == "ESCALATED" and rng.state.writes_applied == 0
