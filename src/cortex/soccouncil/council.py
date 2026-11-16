"""Autonomous SOC Council: routed specialists, mandatory challenge, evidence-bound output (capability 11).

Military/tactical context:
A SOC verdict that cannot cite its evidence cannot be trusted, and a high-impact verdict
nobody tried to refute should not drive action. The council:

1. **routes by trusted case type** (set by SOC code, never by alert text) to a set of
   specialist analysts;
2. has each specialist emit structured claims that cite case evidence ids;
3. for every high-impact claim, runs the existing ACE cross-examination
   (``src/cortex/ace.cross_examine``): grounding filter, distinct-family challenger,
   refutation, reliability record;
4. returns only accepted, evidence-bound claims plus *proposed* follow-ups for Cortex
   capabilities. The council never executes anything ("the model is not the authority").

Analysts implement the same ``complete(system, user)`` surface as model engines, speaking
the ACE line protocol (``CLAIM|ev,...|text`` and ``REFUTE|ev|text``). Today every analyst is
deterministic (family ``rules-*``): no language model is admitted for this deployment, and
quarantined weights are never loaded. ``model_slot`` admits an LLM analyst only when the
model-admission policy marks its engine routable; until then the council says so in every
result.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.cortex.ace import ReliabilityStore, cross_examine
from src.cortex.cybertwin import build_twin

FRESHNESS = timedelta(hours=24)
HIGH = ("high", "critical")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str  # decoy | agent | drift | finding | route | receipt
    observed_at: datetime
    data: Mapping[str, Any]


@dataclass
class Case:
    case_id: str
    case_type: str  # trusted: alert_triage | attack_path | change_review
    now: datetime
    evidence: List[Evidence]
    untrusted_text: Dict[str, str] = field(default_factory=dict)  # alert bodies: never read by analysts

    def by_kind(self, kind: str) -> List[Evidence]:
        return [e for e in self.evidence if e.kind == kind]

    def get(self, eid: str) -> Optional[Evidence]:
        return next((e for e in self.evidence if e.evidence_id == eid), None)


@dataclass
class Claim:
    kind: str  # host_compromised | path_to_asset | agent_misuse | unauthorized_change
    subject: str
    evidence_ids: List[str]
    severity: str
    detail: Dict[str, Any] = field(default_factory=dict)
    analyst: str = ""

    @property
    def text(self) -> str:
        return f"{self.kind}:{self.subject}"


# ---- specialists ------------------------------------------------------------------------------

class Analyst:
    """Deterministic analyst speaking the ACE protocol. ``case`` is bound per run."""

    role = "analyst"
    family = "rules-specialist"

    def __init__(self) -> None:
        self.engine_id = f"rules:{self.role}"
        self.case: Optional[Case] = None
        self.context: Dict[str, Any] = {}

    def claims(self, case: Case) -> List[Claim]:
        raise NotImplementedError

    def complete(self, system_prompt: str, user_prompt: str) -> str:  # ACE proposer surface
        assert self.case is not None
        return "\n".join(f"CLAIM|{','.join(c.evidence_ids)}|{c.text}" for c in self.claims(self.case))


class DeceptionAnalyst(Analyst):
    role = "deception"

    def claims(self, case: Case) -> List[Claim]:
        out = []
        for e in case.by_kind("decoy"):
            sev = "high" if e.data["max_depth"] >= 2 else "medium"
            out.append(Claim("host_compromised", e.data["source"], [e.evidence_id], sev,
                             {"depth": e.data["max_depth"], "count": e.data["count"]}, self.role))
        return out


class AgentAnalyst(Analyst):
    role = "agentshield"

    def claims(self, case: Case) -> List[Claim]:
        out = []
        for e in case.by_kind("agent"):
            if not e.data.get("cusum_alarm"):
                continue
            sev = "high" if e.data.get("denied_calls", 0) > 0 else "medium"
            out.append(Claim("agent_misuse", e.data["agent_id"], [e.evidence_id], sev, dict(e.data), self.role))
        return out


class FabricAnalyst(Analyst):
    role = "fabric"

    def claims(self, case: Case) -> List[Claim]:
        return [Claim("unauthorized_change", e.data["component"], [e.evidence_id], "high", dict(e.data), self.role)
                for e in case.by_kind("drift")]


class ExposureAnalyst(Analyst):
    """Best attack path from each suspected host to protected assets, on the twin built from case evidence."""

    role = "exposure"

    def claims(self, case: Case) -> List[Claim]:
        routes_ev = {e.data["route"]["id"]: e for e in case.by_kind("route")}
        if not routes_ev:
            return []
        mission = self.context["mission"]
        findings = [e.data["finding"] for e in case.by_kind("finding")]
        fev = {e.data["finding"]["host"]: e.evidence_id for e in case.by_kind("finding")}
        suspects = {e.data["source"]: e.evidence_id for e in case.by_kind("decoy")}
        twin = build_twin([e.data["route"] for e in routes_ev.values()], findings, mission)
        out = []
        for host, sev_id in sorted(suspects.items()):
            if host not in twin.nodes:
                continue
            for asset in sorted(twin.protected):
                p = twin.max_path_prob(host, asset)
                if p < self.context.get("min_path_p", 0.05):
                    continue
                from src.cortex.breachpath.optimizer import best_path_edges

                path = best_path_edges(twin, host, asset)
                rids = [twin.route_meta[e].route_id for e in path if e in twin.route_meta]
                ev = [sev_id] + [routes_ev[r].evidence_id for r in rids if r in routes_ev]
                ev += sorted({fev[twin.edges[e].target] for e in path if twin.edges[e].target in fev})
                out.append(Claim("path_to_asset", f"{host}->{asset}", ev, "critical" if p >= 0.2 else "high",
                                 {"p": round(p, 4), "routes": rids}, self.role))
        return out


# ---- challenger -----------------------------------------------------------------------------

class Challenger:
    """Distinct-family refuter. Each rule names the counter-evidence it relied on."""

    role = "challenger"
    family = "rules-challenger"
    engine_id = "rules:challenger"

    def __init__(self, *, scanners: Sequence[str] = ()) -> None:
        self.scanners = set(scanners)
        self.case: Optional[Case] = None
        self.claims_by_text: Dict[str, Claim] = {}
        self.reasons: Dict[str, str] = {}

    def refute(self, c: Claim, case: Case) -> Optional[str]:
        evs = [case.get(e) for e in c.evidence_ids]
        if any(e is None for e in evs):
            return "cites evidence outside the case"
        stale = [e.evidence_id for e in evs if case.now - e.observed_at > FRESHNESS]
        if stale:
            return f"stale evidence {stale}"
        if c.kind in ("host_compromised", "path_to_asset"):
            touch = next(e for e in evs if e.kind == "decoy")
            if touch.data["source"] in self.scanners:
                return f"source {touch.data['source']} is an authorised scanner"
            if touch.data["max_depth"] == 0 and touch.data["count"] == 1:
                return "single connect-only touch: insufficient"
        if c.kind == "path_to_asset":
            current = {e.data["route"]["id"]: e for e in case.by_kind("route_current")}
            dead = [r for r in c.detail["routes"] if r in current and current[r].data["route"]["status"] == "expired"]
            if dead:
                return f"path uses routes expired since: {dead}"
        if c.kind == "unauthorized_change":
            rc = [e for e in case.by_kind("receipt") if e.data.get("component") == c.subject]
            if rc:
                return f"approved change receipt {rc[0].evidence_id}"
        if c.kind == "agent_misuse":
            if c.detail.get("maintenance_window") and not c.detail.get("denied_calls"):
                return "alarm inside a declared maintenance window with no denied call"
        return None

    def complete(self, system_prompt: str, user_prompt: str) -> str:  # ACE challenger surface
        assert self.case is not None
        lines = []
        for line in user_prompt.splitlines():
            if not line.startswith("CLAIM|"):
                continue
            _, ev, text = line.split("|", 2)
            claim = self.claims_by_text.get(text)
            reason = self.refute(claim, self.case) if claim else "unknown claim"
            if reason:
                self.reasons[text] = reason
                lines.append(f"REFUTE|{ev}|{text}")
        return "\n".join(lines)


# ---- council --------------------------------------------------------------------------------

ROUTING: Dict[str, List[str]] = {
    "alert_triage": ["deception", "agentshield"],
    "attack_path": ["deception", "exposure"],
    "change_review": ["fabric"],
}


@dataclass
class CouncilResult:
    case_id: str
    case_type: str
    accepted: List[Dict[str, Any]]
    refuted: List[Dict[str, Any]]
    low_impact: List[Dict[str, Any]]
    proposed_followups: List[Dict[str, Any]]
    analysts: List[str]
    model_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


FOLLOWUP = {
    "host_compromised": ("ghostshift.trigger + wargame playbook", "rotate secrets on the host; evaluate containment"),
    "path_to_asset": ("breachpath.optimize", "close the path with the cheapest approved route changes"),
    "agent_misuse": ("agentshield.enforce", "cut the agent to its purpose profile"),
    "unauthorized_change": ("autoheal.run", "restore the approved state"),
}


class SOCCouncil:
    def __init__(self, *, reliability: ReliabilityStore, mission: Mapping[str, Any], scanners: Sequence[str] = (),
                 challenge: bool = True, model_slot: Optional[Callable[[], Optional[Any]]] = None) -> None:
        self.analysts: Dict[str, Analyst] = {a.role: a for a in (DeceptionAnalyst(), AgentAnalyst(), FabricAnalyst(),
                                                                 ExposureAnalyst())}
        for a in self.analysts.values():
            a.context = {"mission": mission}
        self.challenger = Challenger(scanners=scanners)
        self.reliability = reliability
        self.challenge = challenge
        self.model = model_slot() if model_slot else None

    @property
    def model_status(self) -> str:
        if self.model is None:
            return "deterministic analysts only: no language model admitted for this deployment"
        return f"model analyst admitted: {getattr(self.model, 'engine_id', 'unknown')}"

    def run(self, case: Case) -> CouncilResult:
        roles = ROUTING.get(case.case_type)
        if roles is None:
            raise KeyError(f"untrusted or unknown case type {case.case_type!r}")
        allowed = [e.evidence_id for e in case.evidence]
        accepted, refuted, low = [], [], []
        for role in roles:
            analyst = self.analysts[role]
            analyst.case = case
            claims = analyst.claims(case)
            high = [c for c in claims if c.severity in HIGH]
            low += [self._out(c) for c in claims if c.severity not in HIGH]
            if not high:
                continue
            if not self.challenge:
                accepted += [self._out(c) for c in high]
                continue
            self.challenger.case = case
            self.challenger.claims_by_text = {c.text: c for c in high}
            self.challenger.reasons = {}
            proposer = _OnlyHigh(analyst, high)
            ace = cross_examine(evidence_ids=allowed, case_evidence={}, proposer=proposer, challenger=self.challenger,
                                reliability=self.reliability, system_prompt="SOC council (deterministic)",
                                user_prompt=f"CASE {case.case_id} TYPE {case.case_type}", task_domain=case.case_type)
            by_text = {c.text: c for c in high}
            for ac in ace.claims:
                c = by_text[ac.text]
                if ac.accepted:
                    accepted.append(self._out(c))
                else:
                    refuted.append(self._out(c) | {"reason": self.challenger.reasons.get(ac.text, "")})
        followups = [{"claim": a["text"], "capability": FOLLOWUP[a["kind"]][0], "proposal": FOLLOWUP[a["kind"]][1],
                      "requires": "operator approval through the normal change path"} for a in accepted]
        return CouncilResult(case.case_id, case.case_type, accepted, refuted, low, followups, roles, self.model_status)

    @staticmethod
    def _out(c: Claim) -> Dict[str, Any]:
        return {"text": c.text, "kind": c.kind, "subject": c.subject, "severity": c.severity,
                "evidence_ids": list(c.evidence_ids), "analyst": c.analyst, "detail": json.loads(json.dumps(c.detail))}


class _OnlyHigh:
    """Proposer view restricted to the high-impact claims (low-impact ones skip the challenge)."""

    def __init__(self, analyst: Analyst, claims: Sequence[Claim]) -> None:
        self.role, self.family, self.engine_id = analyst.role, analyst.family, analyst.engine_id
        self._claims = claims

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "\n".join(f"CLAIM|{','.join(c.evidence_ids)}|{c.text}" for c in self._claims)


def model_slot_from_policy(engine_id: str, *, engines_path: Optional[str] = None) -> Callable[[], Optional[Any]]:
    """Admit an LLM analyst only if the admission policy marks the engine routable. Never loads weights here."""
    from src.cortex.model_admission import is_engine_routable

    def factory():
        if not is_engine_routable(engine_id, engines_path):
            return None
        return type("AdmittedModel", (), {"engine_id": engine_id, "family": "llm"})()

    return factory


__all__ = ["AgentAnalyst", "Case", "Challenger", "Claim", "CouncilResult", "DeceptionAnalyst", "Evidence",
           "ExposureAnalyst", "FabricAnalyst", "ROUTING", "SOCCouncil", "model_slot_from_policy"]
