"""Cortex vertical slice: CyberTwin -> architect -> approvals -> broker -> verify -> rollback.

Military/tactical context:
These tests pin the safety properties a commander relies on when Cortex proposes network
changes: no write without bound, fresh, human approval; no disruption of required flows;
silent control-plane failures detected from observed state and rolled back; irreversible
changes never attempted after an earlier failure. Everything runs against the in-repo
mock XiiD MCP server on loopback with a synthetic enterprise.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import httpx
import pytest
import yaml

from range.run_cortex_slice import MISSION, SCENARIO, mock_xiid, run_cycle
from s3m_core.defense.audit.merkle_log import MerkleAuditLog
from src.cortex.architect import propose_options, recommended
from src.cortex.cybertwin import build_twin
from src.cortex.tool_map import XiidToolMap
from src.cortex.transport_mcp import MockHttpMCPTransport
from src.cortex.xiid_broker import EnvelopeRejected, ManifestPinMismatch, XiidMCPBroker
from src.cortex.xiid_write_envelope import WriteEnvelope

pytestmark = pytest.mark.cortex


@pytest.fixture(scope="module")
def scenario():
    return yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mission():
    return yaml.safe_load(MISSION.read_text(encoding="utf-8"))


@pytest.fixture
def xiid():
    with mock_xiid() as handle:
        yield handle


# ---------------------------------------------------------------- twin / architect
def test_enterprise_range_meets_directive_targets(scenario, mission) -> None:
    roles = [h["role"] for h in scenario["hosts"]]
    assert len(scenario["hosts"]) == 200
    assert len([h for h in scenario["hosts"] if h["id"].startswith("srv-")]) == 20
    assert len(mission["applications"]) == 10
    assert any(r["sealed_tunnel"] for r in scenario["routes"]) and scenario["stlinks"]
    assert "camera" in roles and "admin-workstation" in roles


def test_twin_baseline_and_findings(scenario, mission) -> None:
    twin = build_twin(scenario["routes"], scenario["vulnerabilities"], mission)
    assert twin.broken_flows() == []
    top = twin.top_attack_paths(1)[0]
    assert top["nodes"] == ["grp:corp-users", "srv-erp-db-01"]  # planted legacy direct-DB route
    unnecessary = {m.route_id for m in twin.unnecessary_routes()}
    assert {"rt-users-erpdb", "rt-inet-jump-ssh", "rt-cams-corp"} <= unnecessary


def test_architect_options_and_recommendation(scenario, mission) -> None:
    twin = build_twin(scenario["routes"], scenario["vulnerabilities"], mission)
    options = {o.option_id: o for o in propose_options(twin)}
    assert all(o.required_flows_ok for o in options.values())
    assert options["OPT-A"].irreversible_changes == 0
    choice = recommended(list(options.values()))
    assert choice is not None and choice.option_id == "OPT-B"
    assert choice.disrupted_sessions_30d == 0
    assert choice.risk_reduction >= 0.9 * max(o.risk_reduction for o in options.values())
    # Never proposes expiring a route that a required flow depends on.
    required_routes = {f["route"] for f in mission["required_flows"]}
    for o in options.values():
        for ch in o.changes:
            if ch.xiid_action == "expire_route":
                assert ch.route_id not in required_routes


# ---------------------------------------------------------------- full cycle
def test_sim002_cycle_verified(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    report, broker = asyncio.run(run_cycle(url, bearer, workdir=tmp_path, case_id="t-sim002"))
    assert report.outcome == "verified"
    assert report.verification["matches_prediction"] is True
    assert report.verification["observed_broken_flows"] == []
    assert report.verification["observed_system_risk"] < report.twin["system_risk"]
    assert report.audit["merkle_chain_intact"] is True
    for ch in report.changes:
        assert ch["state"] == "verified"
        auth = ch["authorization"]
        if not ch["reversible"]:
            assert auth["change_class"] == "D" and len(auth["votes"]) >= 2
        assert auth["write_envelope"]["args_digest"] and auth["write_envelope"]["expires_at"]
    # Reversible changes executed before irreversible ones.
    order = [c["reversible"] for c in report.changes]
    assert order == sorted(order, reverse=True)
    expired = {r["id"] for r in state.model.list_routes() if r["status"] == "expired"}
    assert expired == {c["route_id"] for c in report.changes if c["xiid_action"] == "expire_route"}


def test_sim005_silent_write_failure_detected_and_rolled_back(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    baseline_routes = {r["id"]: (r["status"], r["narrow_to"]) for r in state.model.list_routes()}
    state.drop_next_write = True
    state.drop_write_skip = 1
    report, _ = asyncio.run(run_cycle(url, bearer, workdir=tmp_path, case_id="t-sim005"))
    assert report.outcome == "rolled_back"
    assert report.verification["failure"]["reason"] == "postcondition_mismatch"
    assert report.verification["failure"]["tool_acknowledged"] is True
    assert report.rollback["restored"] is True
    assert report.rollback["system_risk_after_rollback"] == pytest.approx(report.twin["system_risk"])
    assert report.rollback["broken_flows_after_rollback"] == []
    assert state.metrics.tool_calls.get("route.expire", 0) == 0  # irreversible never attempted
    assert {c["state"] for c in report.changes if not c["reversible"]} == {"cancelled"}
    # Effective policy identical to baseline (narrowed back to the original prefix).
    for r in state.model.list_routes():
        status, narrow_to = baseline_routes[r["id"]]
        assert r["status"] == status or r["narrow_to"] == r["prefix"]


def test_human_denial_blocks_irreversible_changes(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid

    def deny_irreversible(payload):
        return "DENY" if payload["change_class"] == "D" else "APPROVE"

    report, _ = asyncio.run(
        run_cycle(url, bearer, workdir=tmp_path, case_id="t-deny", board_policy=deny_irreversible)
    )
    assert report.outcome == "verified"
    states = {c["xiid_action"]: set() for c in report.changes}
    for c in report.changes:
        states[c["xiid_action"]].add(c["state"])
    assert states["expire_route"] == {"denied"}
    assert states["narrow_route"] == {"verified"}
    assert state.metrics.tool_calls.get("route.expire", 0) == 0


def test_kill_switch_prevents_all_writes(xiid, tmp_path: Path, monkeypatch) -> None:
    url, bearer, state = xiid
    from src.cortex.change_control_gate import ChangeControlGate

    monkeypatch.setattr(ChangeControlGate, "assert_writes_allowed", lambda self: (_ for _ in ()).throw(
        RuntimeError("policy_gate_kill_engaged")))
    report, _ = asyncio.run(run_cycle(url, bearer, workdir=tmp_path, case_id="t-kill"))
    assert report.outcome == "no_action"
    assert state.metrics.write_calls == 0


# ---------------------------------------------------------------- SIM-004: broker hardening
def _broker(url, bearer, tmp_path, key, *, bound=True):
    return XiidMCPBroker(
        transport=MockHttpMCPTransport(url, bearer),
        tool_map=XiidToolMap.from_yaml(),
        audit_log=MerkleAuditLog(str(tmp_path / "a.jsonl")),
        session_id="s4",
        envelope_signing_key=key,
        require_bound_envelopes=bound,
    )


def test_unbound_envelope_rejected_when_binding_required(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    key = secrets.token_bytes(32)
    broker = _broker(url, bearer, tmp_path, key)
    env = WriteEnvelope.issue(operator_id="op", session_id="s4", action="expire_route", signing_key=key)

    async def go():
        await broker.connect_and_pin_manifest()
        with pytest.raises(EnvelopeRejected):
            await broker.invoke("expire_route", {"route_id": "rt-users-erpdb"}, envelope=env)

    asyncio.run(go())
    assert state.metrics.write_calls == 0


def test_bound_envelope_cannot_be_replayed_on_other_target(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    key = secrets.token_bytes(32)
    broker = _broker(url, bearer, tmp_path, key)
    env = WriteEnvelope.issue(
        operator_id="op", session_id="s4", action="expire_route", signing_key=key,
        arguments={"route_id": "rt-mail-file"}, ttl_seconds=60,
    )

    async def go():
        await broker.connect_and_pin_manifest()
        with pytest.raises(EnvelopeRejected):
            await broker.invoke("expire_route", {"route_id": "rt-users-dc"}, envelope=env)  # required flow!
        await broker.invoke("expire_route", {"route_id": "rt-mail-file"}, envelope=env, idempotency_key="k1")

    asyncio.run(go())
    routes = {r["id"]: r["status"] for r in state.model.list_routes()}
    assert routes["rt-users-dc"] == "active" and routes["rt-mail-file"] == "expired"


def test_expired_and_tampered_envelopes_rejected(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    key = secrets.token_bytes(32)
    broker = _broker(url, bearer, tmp_path, key)
    args = {"route_id": "rt-mail-file"}
    expired = WriteEnvelope.issue(operator_id="op", session_id="s4", action="expire_route",
                                  signing_key=key, arguments=args, ttl_seconds=-1)
    good = WriteEnvelope.issue(operator_id="op", session_id="s4", action="expire_route",
                               signing_key=key, arguments=args, ttl_seconds=60)
    from dataclasses import replace

    tampered = replace(good, args_digest="0" * 64)

    async def go():
        await broker.connect_and_pin_manifest()
        for env in (expired, tampered):
            with pytest.raises(EnvelopeRejected):
                await broker.invoke("expire_route", args, envelope=env)

    asyncio.run(go())
    assert state.metrics.write_calls == 0


def test_legacy_unbound_envelope_still_verifies() -> None:
    key = secrets.token_bytes(32)
    env = WriteEnvelope.issue(operator_id="op", session_id="s", action="narrow_route", signing_key=key)
    assert env.verify(key) and not env.is_bound and env.covers_arguments({"anything": 1})


def test_rug_pull_blocks_writes_mid_session(xiid, tmp_path: Path) -> None:
    url, bearer, state = xiid
    key = secrets.token_bytes(32)
    broker = _broker(url, bearer, tmp_path, key)
    args = {"route_id": "rt-mail-file"}
    env = WriteEnvelope.issue(operator_id="op", session_id="s4", action="expire_route",
                              signing_key=key, arguments=args, ttl_seconds=60)

    async def go():
        await broker.connect_and_pin_manifest()
        httpx.post(url.removesuffix("/mcp") + "/admin/rug-pull", json={"tool_name": "route.expire"})
        with pytest.raises(ManifestPinMismatch):
            await broker.invoke("expire_route", args, envelope=env)

    asyncio.run(go())
    assert state.metrics.write_calls == 0
