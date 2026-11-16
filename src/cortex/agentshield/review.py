"""AgentShield access review: purpose-to-permission mapping and least privilege (capability 04).

Military/tactical context:
An AI agent that holds more than its mission needs turns one prompt injection into a
network-wide incident. This module compares what each agent is GRANTED (tools through its
sandbox and scopes, resources through selectors, network through routes from its host)
with what its PURPOSE needs, measures the excess - including the blast radius a hijacked
agent would have - and derives a least-privilege sandbox profile plus the route changes
that would remove excess network reach. It decides nothing alone: the profile is installed
and the routes are changed only through the normal approval path.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import yaml

from src.cortex.architect import ProposedChange
from src.cortex.cybertwin import build_twin
from src.cortex.mcp_contract.authz import SandboxProfile
from src.cortex.mcp_contract.manifest import ContractManifest

ROOT = Path(__file__).resolve().parents[3]
PURPOSES_FILE = ROOT / "configs" / "cortex" / "agent_purposes.yaml"
CLASS_WEIGHT = {"A": 1, "B": 2, "C": 4, "D": 8}
SCOPE_FOR_CLASS = {"A": "cortex.read", "B": "cortex.simulate", "C": "cortex.write.c", "D": "cortex.write.d"}


@dataclass(frozen=True)
class Purpose:
    purpose_id: str
    tools: List[str]
    resources: Mapping[str, Mapping[str, List[str]]]
    network_targets: List[str]
    max_writes_per_hour: int
    redact_fields: List[str]

    def resource_allowed(self, kind: str, rid: str) -> bool:
        sel = self.resources.get(kind)
        if sel is None:
            return False
        if any(fnmatch.fnmatchcase(rid, p) for p in sel.get("deny", [])):
            return False
        return any(fnmatch.fnmatchcase(rid, p) for p in sel.get("allow", []))


def load_purposes(path: Path = PURPOSES_FILE) -> Dict[str, Purpose]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["purposes"]
    return {pid: Purpose(pid, list(p["tools"]), p.get("resources", {}), list(p.get("network_targets", [])),
                         int(p.get("max_writes_per_hour", 0)), list(p.get("redact_fields", [])))
            for pid, p in raw.items()}


@dataclass
class AgentRecord:
    agent_id: str
    owner: str
    purpose: str
    host: str
    sandbox: str


def load_agents(path: Path) -> List[AgentRecord]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [AgentRecord(a["id"], a["owner"], a["purpose"], a["host"], a["sandbox"]) for a in raw["agents"]]


@dataclass
class AccessReview:
    agent_id: str
    purpose: str
    granted_tools: List[str]
    needed_tools: List[str]
    excess_tools: Dict[str, List[str]]  # class -> tools
    missing_tools: List[str]  # purpose needs it but the grant does not allow it
    excess_resources: Dict[str, List[str]]  # kind -> resource ids the grant reaches beyond purpose
    used_outside_purpose: List[str]  # observed calls the purpose does not justify
    granted_routes: List[str]
    excess_routes: List[str]
    blast_radius: Dict[str, float]  # protected asset -> max path probability from the agent host
    blast_radius_least_privilege: Dict[str, float]
    excess_score: float
    verdict: str  # least_privilege | excessive | under_privileged
    recommended_sandbox: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def granted_tools(contract: ContractManifest, profile: SandboxProfile) -> List[str]:
    """Tools a token for this sandbox could successfully call (class, scope and name)."""
    out = []
    for name in sorted(contract.tools):
        spec = contract.tool(name)
        if spec.tool_class in profile.classes and spec.scope in profile.scopes and profile.tool_allowed(name):
            out.append(name)
    return out


def _resource_universe(routes: Sequence[Mapping[str, Any]], stlinks: Sequence[Mapping[str, Any]],
                       hosts: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
    return {"route": [r["id"] for r in routes], "stlink": [s["id"] for s in stlinks], "host": [h["id"] for h in hosts]}


def _blast_radius(routes: Sequence[Mapping[str, Any]], findings: Sequence[Mapping[str, Any]],
                  mission: Mapping[str, Any], host: str) -> Dict[str, float]:
    m = dict(mission, footholds=[host])
    twin = build_twin([r for r in routes], findings, m)
    return {a: round(twin.max_path_prob(host, a), 6) for a in sorted(twin.protected)}


def review_agent(agent: AgentRecord, purpose: Purpose, *, contract: ContractManifest,
                 sandboxes: Mapping[str, SandboxProfile], routes: Sequence[Mapping[str, Any]],
                 stlinks: Sequence[Mapping[str, Any]], hosts: Sequence[Mapping[str, Any]],
                 findings: Sequence[Mapping[str, Any]], mission: Mapping[str, Any],
                 observed_calls: Sequence[Mapping[str, Any]] = ()) -> AccessReview:
    profile = sandboxes[agent.sandbox]
    granted = granted_tools(contract, profile)
    needed = sorted(purpose.tools)
    excess: Dict[str, List[str]] = {}
    for t in sorted(set(granted) - set(needed)):
        excess.setdefault(contract.tool(t).tool_class, []).append(t)
    missing = sorted(set(needed) - set(granted))

    # Resources the grant reaches (through tools that take that resource kind) beyond purpose.
    universe = _resource_universe(routes, stlinks, hosts)
    kinds = {k for t in granted for k in contract.tool(t).resource_args.values()}
    excess_res = {}
    for kind in sorted(kinds):
        extra = [rid for rid in universe.get(kind, [])
                 if profile.resource_allowed(kind, rid) and not purpose.resource_allowed(kind, rid)]
        if extra:
            excess_res[kind] = extra

    used_outside = sorted({c["tool"] for c in observed_calls
                           if c.get("client_id") == agent.agent_id and c["tool"] not in purpose.tools})

    mine = [r for r in routes if r.get("source") == agent.host and r.get("status") != "expired"]
    excess_routes = sorted(r["id"] for r in mine if r["target"] not in purpose.network_targets)
    blast = _blast_radius(routes, findings, mission, agent.host)
    lp_routes = [dict(r, status="expired") if r["id"] in excess_routes else r for r in routes]
    blast_lp = _blast_radius(lp_routes, findings, mission, agent.host)

    tool_score = sum(CLASS_WEIGHT[c] * len(ts) for c, ts in excess.items())
    res_score = sum(math.log2(1 + len(v)) for v in excess_res.values())
    net_score = 10 * sum(max(0.0, blast[a] - blast_lp.get(a, 0.0)) for a in blast)
    score = round(tool_score + res_score + net_score, 3)
    if missing:
        verdict = "under_privileged"
    elif any(c in excess for c in ("C", "D")) or excess_routes or net_score > 0:
        verdict = "excessive"
    elif score > 0:
        verdict = "excessive"
    else:
        verdict = "least_privilege"
    return AccessReview(
        agent.agent_id, purpose.purpose_id, granted, needed, excess, missing, excess_res, used_outside,
        sorted(r["id"] for r in mine), excess_routes, blast, blast_lp, score, verdict,
        recommended_sandbox=least_privilege_profile(purpose, contract, observed_calls, agent.agent_id),
    )


def least_privilege_profile(purpose: Purpose, contract: ContractManifest,
                            observed_calls: Sequence[Mapping[str, Any]] = (), agent_id: str = "") -> Dict[str, Any]:
    """A sandbox profile granting exactly the purpose (never widened by observed behaviour)."""
    classes = sorted({contract.tool(t).tool_class for t in purpose.tools})
    per_min = _peak_per_minute([c for c in observed_calls if c.get("client_id") == agent_id])
    kinds = {k for t in purpose.tools for k in contract.tool(t).resource_args.values()}
    return {
        "description": f"AgentShield least-privilege profile for purpose '{purpose.purpose_id}'",
        "environment": "sandbox",
        "scopes": [SCOPE_FOR_CLASS[c] for c in classes],
        "classes": classes,
        "tools": {"allow": list(purpose.tools), "deny": ["*"]},
        "resources": {k: {"allow": list(purpose.resources.get(k, {}).get("allow", [])),
                          "deny": list(purpose.resources.get(k, {}).get("deny", []))} for k in sorted(kinds)},
        "scope_reads": True,
        "require_inverse": True,
        "min_approvals": 1,
        "write_budget": {"max_writes": purpose.max_writes_per_hour, "window_seconds": 3600},
        "rate_limit_per_minute": max(10, 2 * per_min),
        "obligations": {"taint_untrusted_text": True, "redact_fields": list(purpose.redact_fields)},
    }


def _peak_per_minute(calls: Sequence[Mapping[str, Any]]) -> int:
    buckets: Dict[str, int] = {}
    for c in calls:
        buckets[str(c.get("ts", ""))[:16]] = buckets.get(str(c.get("ts", ""))[:16], 0) + 1
    return max(buckets.values(), default=0)


def route_changes(review: AccessReview) -> List[ProposedChange]:
    """Expire the agent's excess routes (inverse: restore). Each still needs approval."""
    return [ProposedChange(
        change_id=f"agentshield-{rid}", route_id=rid, twin_action="remove", xiid_action="expire_route",
        arguments={"route_id": rid}, rollback_action="restore_route", rollback_arguments={"route_id": rid},
        reversible=True, risk_before=max(review.blast_radius.values(), default=0.0),
        risk_after=max(review.blast_radius_least_privilege.values(), default=0.0), cost=1.0,
        disrupted_sessions_30d=0,
        rationale=f"AgentShield: {review.agent_id} purpose '{review.purpose}' does not need {rid}",
        expected_postcondition={"route_id": rid, "status": "expired"},
    ) for rid in review.excess_routes]


__all__ = ["AccessReview", "AgentRecord", "Purpose", "granted_tools", "least_privilege_profile", "load_agents",
           "load_purposes", "review_agent", "route_changes"]
