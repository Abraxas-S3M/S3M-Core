"""GhostShift: rotate what matters, inside the windows, without changing reachability.

Military/tactical context:
Blueprint acceptance proof for capability 02: "A controlled test demonstrates a topology
adjustment with service continuity, audit evidence and no unapproved reachability
expansion." Here the adjustment is secret rotation through the PROPOSED tools; the test
also proves that adversary knowledge harvested before the drill is worthless after it.
"""

from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

pytest.importorskip("ortools")

from range.run_contract_cycle import contract_range, make_cycle  # noqa: E402
from src.cortex.autoheal.healer import AutoHeal, snapshot_baseline  # noqa: E402
from src.cortex.cybertwin import build_twin  # noqa: E402
from src.cortex.ghostshift.ghostshift import (  # noqa: E402
    allocate,
    execute,
    held_time,
    inventory,
    schedule,
    triggered,
    uniform_allocation,
)
from src.cortex.missionguardian.guardian import MissionGuardian, MissionPolicy  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
S = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
M = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
POLICY = MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml")
PROTECTED = ["srv-dc-01", "srv-pki-01", "srv-nvr-01"]
WORKDAY = datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Riyadh"))


def _guard():
    return MissionGuardian(POLICY, build_twin(S["routes"], S["vulnerabilities"], M), {h["id"]: h["group"] for h in S["hosts"]})


def _secrets():
    return inventory(S["routes"], S["stlinks"], S["vulnerabilities"], M, guard=_guard(), protected_targets=PROTECTED)


def test_held_time_matches_monte_carlo() -> None:
    rate, horizon, n = 0.02, 90.0, 3
    rng = random.Random(3)
    L, total = horizon / (n + 1), 0.0
    for _ in range(20000):
        for _ in range(n + 1):
            t = rng.expovariate(rate)
            total += max(0.0, L - t)
    assert held_time(rate, horizon, n) == pytest.approx(total / 20000, rel=0.03)
    assert held_time(rate, horizon, 0) > held_time(rate, horizon, 1) > held_time(rate, horizon, 5)


def test_importance_ranks_secrets_and_skips_useless_rotation() -> None:
    sec = {s.secret_id: s for s in _secrets()}
    assert max(sec.values(), key=lambda s: s.importance).secret_id == "stlink-srv-erp-db-01"
    zero = {k for k, s in sec.items() if s.importance == 0}
    assert zero == {"st-admins-jump", "st-cams-nvr", "stlink-srv-jump-01"}  # not reachable from footholds
    alloc = allocate(list(sec.values()), budget=40)
    assert all(alloc.rotations[k] == 0 for k in zero)  # never rotated, however large the budget


def test_allocation_beats_uniform_rotation() -> None:
    sec = _secrets()
    for budget, gain in [(6, 0.35), (12, 0.45), (24, 0.35)]:
        a, u = allocate(sec, budget=budget), uniform_allocation(sec, budget=budget)
        assert a.status == "OPTIMAL" and sum(a.rotations.values()) <= budget
        assert a.exposure <= (1 - gain) * u.exposure, budget


def test_schedule_uses_windows_and_spacing() -> None:
    sec = _secrets()
    sched = schedule(sec, allocate(sec, budget=12), start=WORKDAY, guard=_guard())
    tier = {s.secret_id: s.tier for s in sec}
    for sid, times in sched.items():
        assert times == sorted(times) and len(set(times)) == len(times)
        if tier[sid] == 1:
            assert all(t.weekday() == 4 and t.hour == 22 for t in times)  # tier 1: Friday 22:00 only
        if tier[sid] == 2:
            assert all(t.hour == 22 for t in times)


def test_compromise_evidence_selects_implicated_secrets() -> None:
    hit = {s.secret_id for s in triggered(_secrets(), {"hosts": ["srv-erp-db-01"]})}
    assert hit == {"stlink-srv-erp-db-01", "st-erp-erpdb", "st-backup-erpdb", "st-jump-erpdb"}


def _drill(rng, tmp_path, ids):
    sec = [s for s in _secrets() if s.secret_id in ids]
    base_routes, base_stlinks = snapshot_baseline(rng.state.model.list_routes(), rng.state.model.list_stlinks())
    cycle, cortex = make_cycle(rng, workdir=tmp_path, case_id="ghostshift", sandbox="sbx-range-full",
                               mission_guard=_guard(), clock=lambda: WORKDAY)
    healer = AutoHeal(cycle=cycle, baseline_routes=base_routes, baseline_stlinks=base_stlinks)

    async def go():
        try:
            return await execute(sec, cycle=cycle, case_id="ghostshift", findings=S["vulnerabilities"], healer=healer)
        finally:
            await cortex.close()

    return asyncio.run(go()), cortex


def test_drill_invalidates_harvested_secrets_with_continuity(tmp_path) -> None:
    with contract_range() as rng:
        loot = rng.admin({"mode": "attacker_harvest", "stlinks": ["stlink-srv-erp-db-01", "stlink-srv-dc-01"],
                          "tunnels": ["st-erp-erpdb"]})
        assert all(rng.admin({"mode": "attacker_replay", **loot})["stlinks"].values())
        rep, cortex = _drill(rng, tmp_path, {"stlink-srv-erp-db-01", "st-erp-erpdb", "stlink-srv-dc-01"})
        replay = rng.admin({"mode": "attacker_replay", **loot})
        log = cortex.write_log
    assert [r["secret"] for r in rep.rotated] == ["st-erp-erpdb", "stlink-srv-erp-db-01"]
    assert all(r["postcondition"] and r["approvals"] >= 2 for r in rep.rotated)  # not reversible -> 2 approvals
    assert rep.skipped_manual == ["stlink-srv-dc-01"]  # identity infrastructure: operator only
    assert replay["stlinks"] == {"stlink-srv-erp-db-01": False, "stlink-srv-dc-01": True}
    assert replay["tunnels"] == {"st-erp-erpdb": False}
    assert rep.routes_unchanged and rep.exposure_after == rep.exposure_before  # no reachability change
    assert rep.continuity == "CLOSED_NO_FAULT"  # every mission flow still healthy
    assert len(log) == 2 and all(e["response"]["receipt"]["signature_b64"] for e in log)  # audit evidence


def test_failed_rotation_stops_the_drill(tmp_path) -> None:
    with contract_range() as rng:
        rng.state.drop_next_write = True
        rep, _ = _drill(rng, tmp_path, {"stlink-srv-erp-db-01", "st-erp-erpdb"})
        assert rng.state.writes_applied == 0
    assert rep.stopped and "postcondition" in rep.stopped and len(rep.rotated) == 1


def test_grace_period_keeps_old_credential_briefly() -> None:
    with contract_range() as rng:
        old = rng.state.fingerprint("stlink-srv-hr-db-01")
        rng.state.grace_until["stlink-srv-hr-db-01:0"] = math.inf
        rng.state.identity_epochs["stlink-srv-hr-db-01"] = 1
        assert rng.admin({"mode": "attacker_replay", "stlinks": {"stlink-srv-hr-db-01": old}})["stlinks"][
            "stlink-srv-hr-db-01"]
