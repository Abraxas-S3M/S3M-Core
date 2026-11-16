"""Intent2Fabric: typed connectivity intents, a controlled-English parser and a compiler
that turns intents into XiiD route changes with a machine-checked proof.

Military/tactical context:
Operators think in intent ("cameras may only talk to the recorder"), not in route ids.
The danger of translating intent with a language model is a confident, wrong change.
Here the translation is deterministic and verified:

1. ``parse`` accepts a small controlled English (four sentence forms), rejects unknown
   names, and renders a canonical sentence back for operator confirmation. A model may
   later *suggest* intents in this language; it is never the authority.
2. ``compile_intents`` finds every route violating each intent and emits the minimal
   change per route (expire, or narrow for prefix intents). Conflicts with required
   mission flows are reported, never silently resolved.
3. ``verify`` re-evaluates every intent over the simulated post-change route set (all
   routes, so the check is exhaustive and exact for these forms), and proves the plan
   is *monotone*: it removes or narrows connectivity, never adds any.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from src.cortex.architect import ArchitectureOption, ProposedChange, apply_changes, asset_exposure
from src.cortex.cybertwin import CyberTwinGraph, RouteEdgeMeta

KINDS = ("only_reach", "only_from", "deny_services", "restrict_prefix")


class IntentError(ValueError):
    pass


@dataclass(frozen=True)
class Intent:
    intent_id: str
    kind: str
    subject: str  # source for only_reach/deny_services/restrict_prefix, target for only_from
    allowed: Tuple[str, ...] = ()  # targets (only_reach) or sources (only_from)
    services: Tuple[str, ...] = ()  # deny_services; optional filter for restrict_prefix
    target: Optional[str] = None  # restrict_prefix
    prefix: Optional[str] = None  # restrict_prefix

    def canonical(self) -> str:
        if self.kind == "only_reach":
            return f"{self.subject} may only reach {', '.join(self.allowed) or 'nothing'}"
        if self.kind == "only_from":
            return f"only {', '.join(self.allowed)} may reach {self.subject}"
        if self.kind == "deny_services":
            return f"no {', '.join(self.services)} from {self.subject}"
        return f"{self.subject} may reach {self.target} over {', '.join(self.services)} only from {self.prefix}"


# --------------------------------------------------------------------------------------
# controlled English
# --------------------------------------------------------------------------------------
_LIST = r"[\w:.\-]+(?:\s*(?:,|and)\s*[\w:.\-]+)*"
PATTERNS = [
    ("only_reach", re.compile(rf"^(?P<s>[\w:.\-]+) may only reach (?P<l>{_LIST}|nothing)$", re.I)),
    ("only_from", re.compile(rf"^only (?P<l>{_LIST}) may reach (?P<s>[\w:.\-]+)$", re.I)),
    ("deny_services", re.compile(rf"^no (?P<l>{_LIST}) from (?P<s>[\w:.\-]+)$", re.I)),
    ("restrict_prefix", re.compile(
        r"^(?P<s>[\w:.\-]+) may reach (?P<t>[\w:.\-]+) over (?P<svc>[\w\-]+) only from (?P<p>[\d./]+)$", re.I)),
]


def _split(items: str) -> Tuple[str, ...]:
    if items.lower() == "nothing":
        return ()
    return tuple(x.strip() for x in re.split(r"\s*(?:,|\band\b)\s*", items) if x.strip())


def parse(sentence: str, intent_id: str, known_nodes: Set[str], known_services: Set[str]) -> Intent:
    text = " ".join(sentence.strip().rstrip(".").split())
    for kind, rx in PATTERNS:
        m = rx.match(text)
        if not m:
            continue
        if kind == "restrict_prefix":
            intent = Intent(intent_id, kind, m["s"], services=(m["svc"].lower(),), target=m["t"], prefix=m["p"])
        elif kind == "deny_services":
            intent = Intent(intent_id, kind, m["s"], services=tuple(s.lower() for s in _split(m["l"])))
        else:
            intent = Intent(intent_id, kind, m["s"], allowed=_split(m["l"]))
        _check(intent, known_nodes, known_services)
        return intent
    raise IntentError(
        f"{intent_id}: not understood. Use one of: '<src> may only reach <a>, <b>' | "
        "'only <a>, <b> may reach <dst>' | 'no <svc>, <svc> from <src>' | "
        "'<src> may reach <dst> over <svc> only from <cidr>'"
    )


def _check(intent: Intent, nodes: Set[str], services: Set[str]) -> None:
    names = [intent.subject, *intent.allowed] + ([intent.target] if intent.target else [])
    unknown = [n for n in names if n not in nodes]
    if unknown:
        hints = {u: sorted(n for n in nodes if u.split(":")[-1].split("-")[0] in n)[:3] for u in unknown}
        raise IntentError(f"{intent.intent_id}: unknown names {unknown}; did you mean {hints}?")
    bad = [s for s in intent.services if s not in services]
    if bad:
        raise IntentError(f"{intent.intent_id}: unknown services {bad}")
    if intent.prefix:
        try:
            ipaddress.ip_network(intent.prefix, strict=True)
        except ValueError as exc:
            raise IntentError(f"{intent.intent_id}: invalid prefix {intent.prefix}") from exc


# --------------------------------------------------------------------------------------
# semantics over the twin's route set
# --------------------------------------------------------------------------------------
def _active(twin: CyberTwinGraph) -> List[RouteEdgeMeta]:
    return [m for eid, m in twin.route_meta.items() if not twin.edges[eid].removed]


def _effective_prefix(meta: RouteEdgeMeta) -> str:
    return meta.narrowed_to if meta.is_narrowed else meta.original_prefix


def violations(intent: Intent, twin: CyberTwinGraph) -> List[RouteEdgeMeta]:
    out = []
    for m in _active(twin):
        if intent.kind == "only_reach" and m.source == intent.subject and m.target not in intent.allowed:
            out.append(m)
        elif intent.kind == "only_from" and m.target == intent.subject and m.source not in intent.allowed:
            out.append(m)
        elif intent.kind == "deny_services" and m.source == intent.subject and (
            m.service in intent.services or m.service == "any"
        ):
            out.append(m)
        elif (intent.kind == "restrict_prefix" and m.source == intent.subject and m.target == intent.target
              and (not intent.services or m.service in intent.services)):
            if not ipaddress.ip_network(_effective_prefix(m)).subnet_of(ipaddress.ip_network(intent.prefix)):
                out.append(m)
    return out


@dataclass
class IntentConflict:
    intent_id: str
    route_id: str
    reason: str


@dataclass
class CompiledIntents:
    intents: List[Intent]
    changes: List[ProposedChange]
    conflicts: List[IntentConflict]
    proof: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"intents": [{**asdict(i), "canonical": i.canonical()} for i in self.intents],
                "changes": [c.to_dict() for c in self.changes],
                "conflicts": [asdict(c) for c in self.conflicts], "proof": self.proof}


def compile_intents(twin: CyberTwinGraph, intents: Sequence[Intent], *,
                    expire_inverse: Optional[str] = None) -> CompiledIntents:
    plan: Dict[str, ProposedChange] = {}
    conflicts: List[IntentConflict] = []
    idx = 0
    for intent in intents:
        for m in violations(intent, twin):
            if m.route_id in plan and plan[m.route_id].xiid_action == "expire_route":
                continue
            if intent.kind == "restrict_prefix":
                idx += 1
                plan[m.route_id] = ProposedChange(
                    change_id=f"int-{idx:02d}-{m.route_id}", route_id=m.route_id, twin_action="harden",
                    xiid_action="narrow_route", arguments={"route_id": m.route_id, "prefix": intent.prefix},
                    rollback_action="narrow_route",
                    rollback_arguments={"route_id": m.route_id, "prefix": m.original_prefix}, reversible=True,
                    risk_before=0.0, risk_after=0.0, cost=1.0, disrupted_sessions_30d=0,
                    rationale=f"{intent.intent_id}: {intent.canonical()}",
                    expected_postcondition={"route_id": m.route_id, "status": "narrowed", "narrow_to": intent.prefix},
                )
                continue
            if m.required_by:
                conflicts.append(IntentConflict(intent.intent_id, m.route_id,
                                                f"route carries required flow(s) {', '.join(m.required_by)}"))
                continue
            idx += 1
            plan[m.route_id] = ProposedChange(
                change_id=f"int-{idx:02d}-{m.route_id}", route_id=m.route_id, twin_action="remove",
                xiid_action="expire_route", arguments={"route_id": m.route_id},
                rollback_action=expire_inverse, rollback_arguments={"route_id": m.route_id} if expire_inverse else None,
                reversible=bool(expire_inverse), risk_before=0.0, risk_after=0.0, cost=1.25,
                disrupted_sessions_30d=m.observed_sessions_30d,
                rationale=f"{intent.intent_id}: {intent.canonical()}",
                expected_postcondition={"route_id": m.route_id, "status": "expired"},
            )
    changes = list(plan.values())
    sim = twin.clone()
    for ch in changes:
        ch.risk_before = round(sim.system_risk(), 6)
        sim = apply_changes(sim, [ch])
        ch.risk_after = round(sim.system_risk(), 6)
    compiled = CompiledIntents(list(intents), changes, conflicts)
    compiled.proof = verify(twin, compiled)
    return compiled


def _edges(twin: CyberTwinGraph) -> Dict[Tuple[str, str, str], ipaddress.IPv4Network]:
    return {(m.source, m.target, m.service): ipaddress.ip_network(_effective_prefix(m)) for m in _active(twin)}


def verify(twin: CyberTwinGraph, compiled: CompiledIntents) -> Dict[str, Any]:
    """Exhaustive check over the simulated post-change route set."""
    after = apply_changes(twin, compiled.changes)
    conflicted = {(c.intent_id, c.route_id) for c in compiled.conflicts}
    per_intent = {}
    for intent in compiled.intents:
        remaining = [m.route_id for m in violations(intent, after) if (intent.intent_id, m.route_id) not in conflicted]
        per_intent[intent.intent_id] = {"satisfied": not remaining, "unexplained_violations": remaining,
                                        "conflicts": sorted(r for i, r in conflicted if i == intent.intent_id)}
    before_e, after_e = _edges(twin), _edges(after)
    expansions = [f"{k}" for k, net in after_e.items() if k not in before_e or not net.subnet_of(before_e[k])]
    return {
        "method": "exhaustive evaluation over all simulated routes (finite, exact for these intent forms)",
        "intents": per_intent,
        "all_satisfied_or_conflicted": all(v["satisfied"] for v in per_intent.values()),
        "monotone_tightening": not expansions,
        "expansions": expansions,
        "required_flows_intact": after.required_flows_reachable(),
        "broken_flows": after.broken_flows(),
        "routes_before": len(before_e),
        "routes_after": len(after_e),
    }


def as_option(twin: CyberTwinGraph, compiled: CompiledIntents) -> ArchitectureOption:
    """Wrap compiled intents so the defense cycle can authorise and execute them."""
    after = apply_changes(twin, compiled.changes)
    return ArchitectureOption(
        option_id="OPT-I", label="operator-intent", expire_policy="intent", changes=compiled.changes,
        initial_risk=round(twin.system_risk(), 6), final_risk=round(after.system_risk(), 6),
        asset_exposure_before=asset_exposure(twin), asset_exposure_after=asset_exposure(after),
        budget_spent=sum(c.cost for c in compiled.changes), required_flows_ok=after.required_flows_reachable(),
        broken_flows=after.broken_flows(), disrupted_sessions_30d=sum(c.disrupted_sessions_30d for c in compiled.changes),
        irreversible_changes=sum(1 for c in compiled.changes if not c.reversible),
        residual_top_paths=[{**p, "probability": round(p["probability"], 6)} for p in after.top_attack_paths(5)],
    )


def load_intents(entries: Sequence[Mapping[str, str]], twin: CyberTwinGraph) -> List[Intent]:
    nodes = set(twin.nodes)
    services = {m.service for m in twin.route_meta.values()} | {"ssh", "rdp", "smb", "telnet", "winrm"}
    return [parse(e["say"], e["id"], nodes, services) for e in entries]
