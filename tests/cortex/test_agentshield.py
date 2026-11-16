"""AgentShield: find the over-privileged agent, cut it to purpose, keep approved work running.

Military/tactical context:
Blueprint acceptance proof for capability 04: "An agent with intentionally excessive tool
and network permissions is identified; unauthorized paths are rejected while approved tasks
continue." Rejections are checked at the control plane (the agent bypasses its client), and
network reach is measured as the blast radius of a hijacked agent host.
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
from src.cortex.agentshield.behavior import evaluate  # noqa: E402
from src.cortex.agentshield.manifest_check import check_server, injection_markers  # noqa: E402
from src.cortex.agentshield.review import load_agents, load_purposes  # noqa: E402
from src.cortex.agentshield.shield import AgentShield  # noqa: E402
from src.cortex.mcp_contract.client import ContractDenied  # noqa: E402
from src.cortex.mcp_contract.manifest import load_contract  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "range/enterprise/agents_enterprise_200.yaml"
SCENARIO = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
MISSION = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
FORGED = "eyJhbGciOiJFZERTQSJ9.eyJmb3JnZWQiOnRydWV9.c2ln"  # well-formed, unsigned approval token
WORKDAY = datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Riyadh"))


def _inventory(rng):
    m = rng.state.model
    return dict(routes=m.list_routes(), stlinks=m.list_stlinks(), hosts=list(m.hosts), findings=m.list_vulns())


def _shield(rng):
    return AgentShield(contract=load_contract(), purposes=load_purposes(), sandboxes=rng.sandboxes, mission=MISSION)


async def _helpdesk_tasks(transport):
    """The helpdesk agent's legitimate work."""
    await transport.call_tool("telemetry.health")
    await transport.call_tool("inventory.list_routes")
    await transport.call_tool("telemetry.flow_summary", {"route_id": "rt-users-erp", "since": "2026-11-16T06:00:00Z",
                                                          "until": "2026-11-16T07:00:00Z", "limit": 50})


async def _denied(transport, name, args):
    try:
        await transport._raw_call(name, args)  # noqa: SLF001 - a hijacked agent skips client pre-checks
    except ContractDenied as exc:
        return exc.code
    return None


@pytest.fixture
def rng():
    with contract_range() as r:
        r.admin({"mode": "add_routes", "routes": yaml.safe_load(REGISTRY.read_text())["agent_routes"]})
        yield r


def test_review_identifies_the_over_privileged_agent(rng) -> None:
    reviews = {r.agent_id: r for r in _shield(rng).review(load_agents(REGISTRY), **_inventory(rng))}
    helpdesk = reviews["agent-helpdesk"]
    assert helpdesk.verdict == "excessive"
    assert set(helpdesk.excess_tools) == {"A", "B", "C", "D"} and len(helpdesk.excess_tools["D"]) == 5
    assert helpdesk.excess_routes == ["rt-ai2-erpdb", "rt-ai2-jump"]
    assert helpdesk.blast_radius["srv-erp-db-01"] > 0.4 and max(helpdesk.blast_radius_least_privilege.values()) == 0
    # It ranks first; the least-excessive agent still has a few unneeded reads flagged.
    ranked = sorted(reviews.values(), key=lambda r: -r.excess_score)
    assert ranked[0].agent_id == "agent-helpdesk" and ranked[-1].excess_score < 10
    assert not any(r.missing_tools for r in reviews.values())


def test_unauthorized_paths_rejected_while_approved_tasks_continue(rng, tmp_path) -> None:
    async def go():
        agent = rng.client(client_id="agent-helpdesk", sandbox="sbx-range-full")
        try:
            await _helpdesk_tasks(agent)
            # Before: the over-privileged grant lets the agent reach a class C read surface it never needs.
            assert await _denied(agent, "inventory.list_hosts", {}) is None
        finally:
            await agent.close()
        shield = _shield(rng)
        reviews = shield.review(load_agents(REGISTRY), observed_calls=rng.state.call_log, **_inventory(rng))
        cycle, cortex = make_cycle(rng, workdir=tmp_path, case_id="agentshield", sandbox="sbx-range-full",
                                   clock=lambda: WORKDAY)
        try:
            report = await shield.enforce(reviews, cycle=cycle, case_id="agentshield", provision=rng.install_sandbox)
        finally:
            await cortex.close()
        assert report.provisioned["agent-helpdesk"] == "sbx-agent-agent-helpdesk"
        assert {(c["route_id"], c["state"]) for c in report.route_changes} == {
            ("rt-ai2-erpdb", "applied"), ("rt-ai2-jump", "applied")}

        agent = rng.client(client_id="agent-helpdesk", sandbox="sbx-agent-agent-helpdesk")
        try:
            await _helpdesk_tasks(agent)  # approved work continues
            codes = {
                "route.expire": await _denied(agent, "route.expire", {"route_id": "rt-users-erp", "idempotency_key": "x" * 16,
                                                                     "approval": FORGED}),
                "stlink.disable": await _denied(agent, "stlink.disable", {"stlink_id": "stlink-srv-dc-01",
                                                                         "idempotency_key": "y" * 16, "approval": FORGED}),
                "inventory.list_hosts": await _denied(agent, "inventory.list_hosts", {}),
                "flow of DC route": await _denied(agent, "telemetry.flow_summary", {"route_id": "rt-users-dc"}),
                "unfiltered flows": await _denied(agent, "telemetry.flow_summary", {}),
            }
        finally:
            await agent.close()
        return codes

    codes = asyncio.run(go())
    assert codes == {"route.expire": "FORBIDDEN_SCOPE", "stlink.disable": "FORBIDDEN_SCOPE",
                     "inventory.list_hosts": "SANDBOX_DENIED", "flow of DC route": "RESOURCE_DENIED",
                     "unfiltered flows": "RESOURCE_DENIED"}
    routes = {r["id"]: r["status"] for r in rng.state.model.list_routes()}
    assert routes["rt-ai2-siem"] == "active" and routes["rt-ai2-erpdb"] == routes["rt-ai2-jump"] == "expired"
    after = {r.agent_id: r for r in _shield(rng).review(load_agents(REGISTRY), **_inventory(rng))}
    assert max(after["agent-helpdesk"].blast_radius.values()) == 0
    denials = [c for c in rng.state.call_log if c["client_id"] == "agent-helpdesk" and c["decision"] == "deny"]
    assert len(denials) == 5  # every rejection happened at the control plane and is logged


def test_existing_profiles_unchanged_by_read_scoping(rng) -> None:
    """Read scoping is opt-in: the observe profile still reads every route's flows."""
    async def go():
        t = rng.client(client_id="observer", sandbox="sbx-observe")
        try:
            return await t.call_tool("telemetry.flow_summary", {"route_id": "rt-users-dc"})
        finally:
            await t.close()
    assert "windows" in asyncio.run(go())


def test_mcp_server_rug_pull_flagged(rng) -> None:
    async def advertised():
        t = rng.client(client_id="inspector", sandbox="sbx-observe")
        try:
            return await t._advertised()  # noqa: SLF001
        finally:
            await t.close()
    contract = load_contract()
    assert check_server(contract, asyncio.run(advertised()))["verdict"] == "pinned"
    rng.admin({"mode": "rug_pull", "tool": "route.narrow"})
    result = check_server(contract, asyncio.run(advertised()))
    assert result["verdict"] == "suspicious" and result["blocked"]
    assert result["injection_markers"] == {"route.narrow": ["mass_action", "override_instruction"]}


def test_contract_descriptions_raise_no_markers() -> None:
    c = load_contract()
    assert all(not injection_markers(c.tool(n).raw["description"]) for n in c.tools)


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_behaviour_monitor_beats_allowlist(seed) -> None:
    routes = [r["id"] for r in SCENARIO["routes"]]
    res = evaluate("ticket_triage", load_purposes()["ticket_triage"].tools, sorted(load_contract().tools),
                   ["rt-users-erp", "rt-users-hr", "rt-vpn-users", "rt-users-file", "rt-inet-vpn"], routes, seed=seed)
    assert res["normal"]["cusum_false_alarm"] <= 0.02
    assert res["recon"]["cusum_detection"] >= 0.95 and res["write"]["cusum_detection"] >= 0.95
    assert res["harvest"]["cusum_detection"] >= 0.95 and res["harvest"]["allowlist_detection"] == 0
    assert res["low_and_slow"]["cusum_detection"] > 0.8 and res["low_and_slow"]["allowlist_detection"] == 0
