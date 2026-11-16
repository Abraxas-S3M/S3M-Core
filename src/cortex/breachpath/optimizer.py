"""BreachPath Eliminator: exact minimum-cost reversible cut of attack paths.

Military/tactical context:
Commanders ask a precise question: "what is the cheapest set of changes that brings every
crown-jewel asset under an acceptable exposure, without breaking a mission flow?" The
greedy MRC planner answers a different question (biggest risk drop per step) and cannot
prove its answer is the cheapest. This module solves the commander's question exactly.

Formulation (constraint programming, OR-Tools CP-SAT, integer-scaled log probabilities):

  variables   n_e in {0,1}   narrow route e (only if a narrower prefix exists)
              x_e in {0,1}   expire route e (only if no required flow depends on it and
                             mission constraints allow); n_e + x_e <= 1
              y_p in {0,1}   path p is cut (some expired edge lies on p)
              z_k >= 0       unavoidable excess for foothold/asset pair k
  path p of pair k, target threshold tau_k:
              y_p <= sum_{e in p} x_e
              sum_{e in p} ln p_e + ln(f) * sum_{e in p} n_e  <=  ln tau_k + M_p * y_p + z_k
  mission:    sum n + x <= max_changes; sum_{irreversible} x <= max_irreversible;
              sum sessions_e * x_e <= max_disrupted_sessions; forbidden actions removed
  phase 1:    minimise sum_k z_k                      (smallest achievable residual exposure)
  phase 2:    fix sum_k z_k at its optimum; minimise change cost + disruption

Attack paths are generated lazily: solve over known paths, apply the plan to the twin,
add every pair's new maximum-probability path that still exceeds its threshold, repeat.
When nothing new appears, the plan is optimal for the full (exponential) path set.

Prior-art note: min-cost attack-graph hardening and lazy path/cut generation are known
techniques. Candidate novelty lies in the combination - mission-flow hard constraints,
reversibility-aware costs, calibrated probabilistic thresholds and a direct mapping to
XiiD control primitives - and requires a prior-art search before any claim.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ortools.sat.python import cp_model

from src.cortex.cybertwin import NARROW_FACTOR, CyberTwinGraph

SCALE = 10_000  # integer units per nat of log-probability
EPS = 1e-9


@dataclass
class PlanConstraints:
    """Hard limits a plan must respect. MissionGuardian produces these."""

    forbidden: Dict[str, Set[str]] = field(default_factory=dict)  # route_id -> {"narrow","expire"}
    expire_policy: str = "unused_only"  # any | unused_only | none
    expire_reversible: bool = False  # True once the control plane implements route.restore
    max_changes: Optional[int] = None
    max_irreversible: Optional[int] = None
    max_disrupted_sessions: Optional[int] = None


@dataclass(frozen=True)
class PlannedAction:
    route_id: str
    action: str  # narrow | expire
    cost: float
    disrupted_sessions_30d: int
    reversible: bool


@dataclass
class ResidualExposure:
    foothold: str
    asset: str
    exposure: float
    threshold: float
    path: List[str]
    blocking: List[str]  # why it cannot be cut: e.g. "identity:...", "required:rt-users-dc"


@dataclass
class BreachPathPlan:
    actions: List[PlannedAction]
    thresholds: Dict[str, float]
    exposure_before: Dict[str, float]
    exposure_after: Dict[str, float]
    total_cost: float
    disrupted_sessions_30d: int
    residual: List[ResidualExposure]
    status: str  # OPTIMAL | FEASIBLE | NO_ACTION_NEEDED
    iterations: int
    paths_generated: int
    solve_seconds: float

    @property
    def meets_thresholds(self) -> bool:
        return not self.residual

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "actions": [a.__dict__ for a in self.actions],
            "total_cost": round(self.total_cost, 4),
            "disrupted_sessions_30d": self.disrupted_sessions_30d,
            "thresholds": self.thresholds,
            "exposure_before": self.exposure_before,
            "exposure_after": self.exposure_after,
            "residual": [r.__dict__ for r in self.residual],
            "iterations": self.iterations,
            "paths_generated": self.paths_generated,
            "solve_seconds": round(self.solve_seconds, 3),
        }


# --------------------------------------------------------------------------------------
# twin helpers
# --------------------------------------------------------------------------------------
def best_path_edges(twin: CyberTwinGraph, source: str, target: str) -> List[str]:
    """Edge ids on the current maximum-probability path (empty if unreachable)."""
    best_log, pred = twin._paths_from(source)  # noqa: SLF001 - shared graph internals
    if target not in best_log or target == source:
        return []
    edges: List[str] = []
    cur, seen = target, set()
    while cur != source and cur in pred and cur not in seen:
        seen.add(cur)
        prev, eid = pred[cur]
        edges.append(eid)
        cur = prev
    return list(reversed(edges))


def exposure(twin: CyberTwinGraph) -> Dict[str, float]:
    return {
        a: round(max((twin.max_path_prob(f, a) for f in twin.footholds), default=0.0), 6)
        for a in sorted(twin.protected)
    }


def apply_actions(twin: CyberTwinGraph, actions: Sequence[PlannedAction]) -> CyberTwinGraph:
    sim = twin.clone()
    for a in actions:
        eid = sim.route_edge[a.route_id]
        if a.action == "expire":
            sim.edges[eid].removed = True
        elif not sim.edges[eid].hardened:
            sim.edges[eid].p *= NARROW_FACTOR
            sim.edges[eid].hardened = True
            sim.route_meta[eid].narrowed_to = sim.route_meta[eid].narrow_candidate
    sim._path_cache.clear()  # noqa: SLF001
    return sim


def _disruption_units(sessions: int) -> int:
    # log-scaled: expiring a route used 10k times costs ~4x one used 10 times, not 1000x.
    return int(round(1000 * math.log10(1 + max(0, sessions))))


def plan_objective(actions: Sequence[PlannedAction]) -> int:
    """The phase-2 objective: change cost, irreversibility and log-scaled disruption.

    Use this, not raw cost, when comparing plans: it is what the solver minimises.
    """
    total = 0
    for a in actions:
        if a.action == "narrow":
            total += 1000
        else:
            total += 1250 + (0 if a.reversible else 500) + _disruption_units(a.disrupted_sessions_30d)
    return total


def _allowed(twin: CyberTwinGraph, c: PlanConstraints) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for eid, meta in twin.route_meta.items():
        edge = twin.edges[eid]
        if edge.removed or edge.effective_p <= 0:
            continue
        acts: Set[str] = set()
        if meta.narrow_candidate and not edge.hardened and not meta.is_narrowed:
            acts.add("narrow")
        if not meta.required_by and c.expire_policy != "none":
            if c.expire_policy == "any" or meta.observed_sessions_30d == 0:
                acts.add("expire")
        acts -= c.forbidden.get(meta.route_id, set())
        if acts:
            out[eid] = acts
    return out


def _blocking(twin: CyberTwinGraph, path: Sequence[str], allowed: Mapping[str, Set[str]]) -> List[str]:
    reasons = []
    for eid in path:
        if eid in allowed:
            continue
        meta = twin.route_meta.get(eid)
        if meta is None:
            reasons.append(eid)  # identity edge
        elif meta.required_by:
            reasons.append(f"required:{meta.route_id} ({', '.join(meta.required_by)})")
        else:
            reasons.append(f"not-actionable:{meta.route_id}")
    return reasons


# --------------------------------------------------------------------------------------
# solver
# --------------------------------------------------------------------------------------
def _solve(
    twin: CyberTwinGraph,
    paths: Dict[Tuple[str, ...], Tuple[str, str]],
    thresholds: Mapping[str, float],
    allowed: Mapping[str, Set[str]],
    c: PlanConstraints,
    time_limit: float,
) -> Tuple[List[PlannedAction], str]:
    m = cp_model.CpModel()
    n: Dict[str, cp_model.IntVar] = {}
    x: Dict[str, cp_model.IntVar] = {}
    for eid, acts in allowed.items():
        if "narrow" in acts:
            n[eid] = m.NewBoolVar(f"n_{eid}")
        if "expire" in acts:
            x[eid] = m.NewBoolVar(f"x_{eid}")
        if eid in n and eid in x:
            m.Add(n[eid] + x[eid] <= 1)

    ln_f = int(round(SCALE * math.log(NARROW_FACTOR)))
    pairs = sorted({k for k in paths.values()})
    z = {k: m.NewIntVar(0, 50 * SCALE, f"z_{k[0]}_{k[1]}") for k in pairs}
    for key, (foot, asset) in paths.items():
        log_p = sum(int(round(SCALE * math.log(max(twin.edges[e].p, 1e-12)))) for e in key)
        log_tau = int(round(SCALE * math.log(max(thresholds[asset], 1e-12))))
        big = max(0, log_p - log_tau) + 1
        cut_vars = [x[e] for e in key if e in x]
        narrow_terms = [ln_f * n[e] for e in key if e in n]
        if cut_vars:
            y = m.NewBoolVar(f"y_{len(key)}_{abs(hash(key)) % 10**9}")
            m.Add(y <= sum(cut_vars))
            m.Add(log_p + sum(narrow_terms) <= log_tau + big * y + z[(foot, asset)])
        else:
            m.Add(log_p + sum(narrow_terms) <= log_tau + z[(foot, asset)])

    metas = {eid: twin.route_meta[eid] for eid in allowed}
    if c.max_changes is not None:
        m.Add(sum(n.values()) + sum(x.values()) <= c.max_changes)
    if c.max_irreversible is not None and not c.expire_reversible:
        m.Add(sum(x.values()) <= c.max_irreversible)
    if c.max_disrupted_sessions is not None:
        m.Add(sum(metas[e].observed_sessions_30d * v for e, v in x.items()) <= c.max_disrupted_sessions)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1  # deterministic
    solver.parameters.random_seed = 7

    # phase 1: smallest achievable residual excess
    m.Minimize(sum(z.values()))
    st1 = solver.Solve(m)
    if st1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"BreachPath model infeasible ({solver.StatusName(st1)})")
    best_excess = int(round(solver.ObjectiveValue()))
    m.Add(sum(z.values()) <= best_excess)

    # phase 2: cheapest plan at that residual (cost x1000 + disruption + irreversibility)
    irreversible_penalty = 0 if c.expire_reversible else 500
    cost_terms = [1000 * v for v in n.values()]
    cost_terms += [
        (1250 + irreversible_penalty + _disruption_units(metas[e].observed_sessions_30d)) * v for e, v in x.items()
    ]
    m.Minimize(sum(cost_terms) if cost_terms else 0)
    st2 = solver.Solve(m)
    status = "OPTIMAL" if st1 == cp_model.OPTIMAL and st2 == cp_model.OPTIMAL else "FEASIBLE"

    actions: List[PlannedAction] = []
    for eid in sorted(allowed):
        meta = metas[eid]
        if eid in n and solver.Value(n[eid]):
            actions.append(PlannedAction(meta.route_id, "narrow", 1.0, 0, True))
        if eid in x and solver.Value(x[eid]):
            actions.append(PlannedAction(meta.route_id, "expire", 1.25, meta.observed_sessions_30d, c.expire_reversible))
    return actions, status


def optimize(
    twin: CyberTwinGraph,
    *,
    threshold: float = 0.10,
    asset_thresholds: Optional[Mapping[str, float]] = None,
    constraints: Optional[PlanConstraints] = None,
    max_iterations: int = 200,
    time_limit: float = 20.0,
) -> BreachPathPlan:
    """Cheapest constraint-respecting plan bringing each asset's exposure to its threshold."""
    c = constraints or PlanConstraints()
    thresholds = {a: float((asset_thresholds or {}).get(a, threshold)) for a in sorted(twin.protected)}
    allowed = _allowed(twin, c)
    before = exposure(twin)
    t0 = time.perf_counter()
    paths: Dict[Tuple[str, ...], Tuple[str, str]] = {}
    actions: List[PlannedAction] = []
    status = "NO_ACTION_NEEDED"
    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        sim = apply_actions(twin, actions)
        new = 0
        for f in sorted(twin.footholds):
            for a in sorted(twin.protected):
                if sim.max_path_prob(f, a) <= thresholds[a] + EPS:
                    continue
                key = tuple(best_path_edges(sim, f, a))
                if key and key not in paths:
                    paths[key] = (f, a)
                    new += 1
        if new == 0:
            break
        actions, status = _solve(twin, paths, thresholds, allowed, c, time_limit)
    else:
        status = "FEASIBLE"  # iteration cap reached; plan valid but optimality unproven

    final = apply_actions(twin, actions)
    after = exposure(final)
    residual: List[ResidualExposure] = []
    for f in sorted(twin.footholds):
        for a in sorted(twin.protected):
            p = final.max_path_prob(f, a)
            if p > thresholds[a] + EPS:
                path = best_path_edges(final, f, a)
                residual.append(ResidualExposure(f, a, round(p, 6), thresholds[a], path, _blocking(final, path, allowed)))
    return BreachPathPlan(
        actions=actions,
        thresholds=thresholds,
        exposure_before=before,
        exposure_after=after,
        total_cost=sum(a.cost for a in actions),
        disrupted_sessions_30d=sum(a.disrupted_sessions_30d for a in actions),
        residual=residual,
        status=status if actions or residual else "NO_ACTION_NEEDED",
        iterations=iterations,
        paths_generated=len(paths),
        solve_seconds=time.perf_counter() - t0,
    )
