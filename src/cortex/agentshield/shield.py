"""AgentShield orchestration: inventory -> review -> least-privilege enforcement (capability 04).

Military/tactical context:
One pass over the agent estate. The MCP servers are checked against the pinned contract.
Every agent is reviewed against its purpose. For each excessive agent, AgentShield
provisions a least-privilege sandbox (through a supplied provisioning hook: in production
an access-review ticket to the XiiD/IdP administrators, in the range a direct install) and
proposes expiring its excess routes. Route changes go through the same device approvals,
approval tokens, broker and postcondition checks as every other Cortex change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Sequence

from src.cortex.agentshield.manifest_check import check_server
from src.cortex.agentshield.review import AccessReview, AgentRecord, Purpose, review_agent, route_changes
from src.cortex.defense_cycle import DefenseCycle
from src.cortex.mcp_contract.authz import SandboxProfile
from src.cortex.mcp_contract.manifest import ContractManifest


@dataclass
class ShieldReport:
    servers: List[Dict[str, Any]] = field(default_factory=list)
    reviews: List[Dict[str, Any]] = field(default_factory=list)
    provisioned: Dict[str, str] = field(default_factory=dict)  # agent -> new sandbox id
    route_changes: List[Dict[str, Any]] = field(default_factory=list)


class AgentShield:
    def __init__(self, *, contract: ContractManifest, purposes: Mapping[str, Purpose],
                 sandboxes: Mapping[str, SandboxProfile], mission: Mapping[str, Any]) -> None:
        self.contract = contract
        self.purposes = purposes
        self.sandboxes = sandboxes
        self.mission = mission

    def check_servers(self, advertised_by_server: Mapping[str, Sequence[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
        return [check_server(self.contract, adv, server_id=sid) for sid, adv in sorted(advertised_by_server.items())]

    def review(self, agents: Sequence[AgentRecord], *, routes, stlinks, hosts, findings,
               observed_calls: Sequence[Mapping[str, Any]] = ()) -> List[AccessReview]:
        return [review_agent(a, self.purposes[a.purpose], contract=self.contract, sandboxes=self.sandboxes,
                             routes=routes, stlinks=stlinks, hosts=hosts, findings=findings, mission=self.mission,
                             observed_calls=observed_calls) for a in agents]

    async def enforce(self, reviews: Sequence[AccessReview], *, cycle: DefenseCycle, case_id: str,
                      provision: Callable[[str, Dict[str, Any]], None]) -> ShieldReport:
        """Provision least-privilege sandboxes and expire excess routes (each change approved)."""
        rep = ShieldReport(reviews=[r.to_dict() for r in reviews])
        await cycle.broker.connect_and_pin_manifest()
        for r in reviews:
            if r.verdict != "excessive":
                continue
            sid = f"sbx-agent-{r.agent_id}"
            provision(sid, r.recommended_sandbox)
            rep.provisioned[r.agent_id] = sid
            for ch in route_changes(r):
                entry = {"agent": r.agent_id, "change_id": ch.change_id, "route_id": ch.route_id,
                         "action": ch.xiid_action}
                try:
                    auth = cycle._authorize(case_id, ch)  # noqa: SLF001 - same approval path as the cycle
                except Exception as exc:  # pragma: no cover - surfaced in report
                    rep.route_changes.append({**entry, "state": f"approval error: {exc}"[:160]})
                    continue
                if not auth.get("gate_satisfied"):
                    rep.route_changes.append({**entry, "state": "denied"})
                    continue
                await cycle.broker.invoke(ch.xiid_action, ch.arguments, envelope=auth["write_envelope"],
                                          idempotency_key=f"{case_id}:{ch.change_id}")
                routes = (await cycle.broker.invoke("list_routes")).result["routes"]
                cur = next((x for x in routes if x["id"] == ch.route_id), {})
                rep.route_changes.append({**entry, "approvals": len(auth.get("votes", [])),
                                          "state": "applied" if cur.get("status") == "expired" else
                                          "postcondition_failed"})
        return rep


__all__ = ["AgentShield", "ShieldReport"]
