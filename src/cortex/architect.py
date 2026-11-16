"""Autonomous Security Architect: alternative architectures from the CyberTwin.

Military/tactical context:
Commanders need options, not a single machine verdict. The architect produces several
candidate security architectures under different disruption policies, simulates each on
the twin, and recommends one by an explicit, auditable rule. Every candidate maps onto
concrete XiiD MCP actions with a declared rollback (or a declared lack of one).

Option policies:
* ``OPT-A reversible-only``   - narrow routes only; every change has an inverse.
* ``OPT-B minimal-disruption`` - expire only routes with zero observed sessions, narrow others.
* ``OPT-C max-reduction``      - expire any route no required flow depends on.

Recommendation rule (deterministic): among options that keep every required flow, keep
those reaching >= ``SUFFICIENCY`` of the best achievable risk reduction; choose the one
disrupting the fewest observed sessions, then fewest irreversible changes, then lowest cost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.cortex.cybertwin import NARROW_FACTOR, CyberTwinGraph
from src.cortex.reachability import MRCAction, plan_mrc

SUFFICIENCY = 0.90
DEFAULT_BUDGET = 8.0

OPTION_POLICIES: Tuple[Tuple[str, str, str], ...] = (
    ("OPT-A", "reversible-only", "none"),
    ("OPT-B", "minimal-disruption", "unused_only"),
    ("OPT-C", "max-reduction", "any"),
)


@dataclass
class ProposedChange:
    """One XiiD-executable change with its inverse, as simulated on the twin."""

    change_id: str
    route_id: str
    twin_action: str  # harden | remove
    xiid_action: str  # narrow_route | expire_route
    arguments: Dict[str, Any]
    rollback_action: Optional[str]
    rollback_arguments: Optional[Dict[str, Any]]
    reversible: bool
    risk_before: float
    risk_after: float
    cost: float
    disrupted_sessions_30d: int
    rationale: str
    expected_postcondition: Dict[str, Any]
    state: str = "proposed"  # proposed -> approved -> executed -> verified | failed | rolled_back

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitectureOption:
    option_id: str
    label: str
    expire_policy: str
    changes: List[ProposedChange]
    initial_risk: float
    final_risk: float
    asset_exposure_before: Dict[str, float]
    asset_exposure_after: Dict[str, float]
    budget_spent: float
    required_flows_ok: bool
    broken_flows: List[str]
    disrupted_sessions_30d: int
    irreversible_changes: int
    residual_top_paths: List[Dict[str, Any]] = field(default_factory=list)
    target_threshold: Optional[float] = None
    residual_exposure: List[Dict[str, Any]] = field(default_factory=list)
    proven_optimal: bool = False
    mission_violations: List[Dict[str, Any]] = field(default_factory=list)
    recommended: bool = False
    state: str = "simulated"

    @property
    def risk_reduction(self) -> float:
        return self.initial_risk - self.final_risk

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_reduction"] = round(self.risk_reduction, 6)
        return d


def asset_exposure(twin: CyberTwinGraph) -> Dict[str, float]:
    """Max path probability from any foothold to each protected asset."""
    return {
        asset: round(max((twin.max_path_prob(f, asset) for f in twin.footholds), default=0.0), 6)
        for asset in sorted(twin.protected)
    }


def _to_change(
    twin: CyberTwinGraph, action: MRCAction, idx: int, expire_inverse: Optional[str] = None
) -> ProposedChange:
    meta = twin.route_meta[action.edge_id]
    if action.action == "harden":
        prefix = str(meta.narrow_candidate)
        return ProposedChange(
            change_id=f"chg-{idx:02d}-{meta.route_id}",
            route_id=meta.route_id,
            twin_action="harden",
            xiid_action="narrow_route",
            arguments={"route_id": meta.route_id, "prefix": prefix},
            rollback_action="narrow_route",
            rollback_arguments={"route_id": meta.route_id, "prefix": meta.original_prefix},
            reversible=True,
            risk_before=round(action.risk_before, 6),
            risk_after=round(action.risk_after, 6),
            cost=action.cost,
            disrupted_sessions_30d=0,
            rationale=(
                f"Narrow {meta.service} access {meta.source} -> {meta.target} from {meta.original_prefix} "
                f"to {prefix}; modelled edge likelihood x{NARROW_FACTOR}. Assumes {prefix} covers all "
                "legitimate consumers (verify against flow logs)."
            ),
            expected_postcondition={"route_id": meta.route_id, "status": "narrowed", "narrow_to": prefix},
        )
    return ProposedChange(
        change_id=f"chg-{idx:02d}-{meta.route_id}",
        route_id=meta.route_id,
        twin_action="remove",
        xiid_action="expire_route",
        arguments={"route_id": meta.route_id},
        # Current XiiD contract: no tool re-activates an expired route. Contract v0.1
        # proposes route.restore; when the control plane implements it, pass it here.
        rollback_action=expire_inverse,
        rollback_arguments={"route_id": meta.route_id} if expire_inverse else None,
        reversible=bool(expire_inverse),
        risk_before=round(action.risk_before, 6),
        risk_after=round(action.risk_after, 6),
        cost=action.cost,
        disrupted_sessions_30d=meta.observed_sessions_30d,
        rationale=(
            f"Expire {meta.service} route {meta.source} -> {meta.target} "
            f"({meta.observed_sessions_30d} sessions in 30d, no required flow depends on it)."
        ),
        expected_postcondition={"route_id": meta.route_id, "status": "expired"},
    )


def apply_changes(twin: CyberTwinGraph, changes: List[ProposedChange]) -> CyberTwinGraph:
    """Return a clone of ``twin`` with ``changes`` applied (simulation only)."""
    sim = twin.clone()
    for ch in changes:
        eid = sim.route_edge[ch.route_id]
        if ch.twin_action == "remove":
            sim.apply_remove(eid)
        else:
            sim.apply_harden(eid, NARROW_FACTOR)
            sim.route_meta[eid].narrowed_to = ch.arguments["prefix"]
    sim._path_cache.clear()
    return sim


def _exact_option(twin: CyberTwinGraph, threshold: float, constraints: Any,
                  expire_inverse: Optional[str]) -> ArchitectureOption:
    """OPT-D: provably cheapest plan meeting the exposure target (BreachPath)."""
    from src.cortex.breachpath.optimizer import PlanConstraints, optimize  # lazy: needs ortools

    c = constraints or PlanConstraints(expire_policy="unused_only", expire_reversible=bool(expire_inverse))
    plan = optimize(twin, threshold=threshold, constraints=c)
    changes: List[ProposedChange] = []
    sim = twin.clone()
    for i, a in enumerate(plan.actions, start=1):
        eid = twin.route_edge[a.route_id]
        before = sim.system_risk()
        mrc = MRCAction(edge_id=eid, action="remove" if a.action == "expire" else "harden",
                        cost=a.cost, disruption=0.0, risk_before=before, risk_after=before)
        sim = apply_changes(sim, [_to_change(twin, mrc, i, expire_inverse)])
        mrc.risk_after = sim.system_risk()
        changes.append(_to_change(twin, mrc, i, expire_inverse))
    final = apply_changes(twin, changes)
    return ArchitectureOption(
        option_id="OPT-D",
        label="exact-minimum",
        expire_policy=c.expire_policy,
        changes=changes,
        initial_risk=round(twin.system_risk(), 6),
        final_risk=round(final.system_risk(), 6),
        asset_exposure_before=asset_exposure(twin),
        asset_exposure_after=asset_exposure(final),
        budget_spent=plan.total_cost,
        required_flows_ok=final.required_flows_reachable(),
        broken_flows=final.broken_flows(),
        disrupted_sessions_30d=sum(ch.disrupted_sessions_30d for ch in changes),
        irreversible_changes=sum(1 for ch in changes if not ch.reversible),
        residual_top_paths=[{**p, "probability": round(p["probability"], 6)} for p in final.top_attack_paths(5)],
        target_threshold=threshold,
        residual_exposure=[r.__dict__ for r in plan.residual],
        proven_optimal=plan.status in {"OPTIMAL", "NO_ACTION_NEEDED"},
    )


def propose_options(
    twin: CyberTwinGraph,
    *,
    budget: float = DEFAULT_BUDGET,
    expire_inverse: Optional[str] = None,
    exact_threshold: Optional[float] = None,
    exact_constraints: Any = None,
    validator: Optional[Callable[[ArchitectureOption], List[Dict[str, Any]]]] = None,
) -> List[ArchitectureOption]:
    before = asset_exposure(twin)
    options: List[ArchitectureOption] = []
    for option_id, label, policy in OPTION_POLICIES:
        variant = twin.with_policy(policy)
        plan = plan_mrc(variant, budget, harden_factor=NARROW_FACTOR)
        changes = [_to_change(variant, a, i, expire_inverse) for i, a in enumerate(plan.actions, start=1)]
        sim = apply_changes(twin, changes)
        options.append(
            ArchitectureOption(
                option_id=option_id,
                label=label,
                expire_policy=policy,
                changes=changes,
                initial_risk=round(plan.initial_risk, 6),
                final_risk=round(sim.system_risk(), 6),
                asset_exposure_before=before,
                asset_exposure_after=asset_exposure(sim),
                budget_spent=plan.budget_spent,
                required_flows_ok=sim.required_flows_reachable(),
                broken_flows=sim.broken_flows(),
                disrupted_sessions_30d=sum(c.disrupted_sessions_30d for c in changes),
                irreversible_changes=sum(1 for c in changes if not c.reversible),
                residual_top_paths=[
                    {**p, "probability": round(p["probability"], 6)} for p in sim.top_attack_paths(5)
                ],
            )
        )
    if exact_threshold is not None:
        options.append(_exact_option(twin, exact_threshold, exact_constraints, expire_inverse))
    if validator is not None:
        for o in options:
            o.mission_violations = validator(o)
    if exact_threshold is not None:
        _mark_recommended_by_target(options)
    else:
        _mark_recommended(options)
    return options


def _mark_recommended_by_target(options: List[ArchitectureOption]) -> None:
    """Target mode: cheapest option reaching the exposure OPT-D proved achievable."""
    exact = next(o for o in options if o.option_id == "OPT-D")
    goal = exact.asset_exposure_after
    meeting = [
        o for o in options
        if o.required_flows_ok and not o.mission_violations and o.changes
        and all(o.asset_exposure_after.get(a, 1.0) <= v + 1e-9 for a, v in goal.items())
    ]
    if not meeting:
        return
    choice = min(meeting, key=lambda o: (o.disrupted_sessions_30d, o.irreversible_changes, o.budget_spent,
                                         len(o.changes), o.option_id))
    choice.recommended = True


def _mark_recommended(options: List[ArchitectureOption]) -> None:
    viable = [o for o in options if o.required_flows_ok and o.changes and not o.mission_violations]
    if not viable:
        return
    best = max(o.risk_reduction for o in viable)
    sufficient = [o for o in viable if o.risk_reduction >= SUFFICIENCY * best - 1e-12]
    choice = min(
        sufficient,
        key=lambda o: (o.disrupted_sessions_30d, o.irreversible_changes, o.budget_spent, o.option_id),
    )
    choice.recommended = True


def recommended(options: List[ArchitectureOption]) -> Optional[ArchitectureOption]:
    return next((o for o in options if o.recommended), None)
