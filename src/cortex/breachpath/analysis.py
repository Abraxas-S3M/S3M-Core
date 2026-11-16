"""BreachPath analysis: greedy baseline, cost/exposure frontier, synthetic scale twins.

Military/tactical context:
An optimiser is only credible if it is measured against the simple method it replaces and
shown to scale to theatre-size networks. These helpers produce those measurements; they
do not change any network.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.cortex.breachpath.optimizer import (
    BreachPathPlan,
    PlanConstraints,
    PlannedAction,
    apply_actions,
    exposure,
    optimize,
    plan_objective,
)
from src.cortex.cybertwin import NARROW_FACTOR, CyberTwinGraph, build_twin
from src.cortex.reachability import plan_mrc


@dataclass
class BaselineResult:
    actions: List[PlannedAction]
    total_cost: float
    reached: bool
    exposure_after: Dict[str, float]
    seconds: float


def greedy_to_threshold(
    twin: CyberTwinGraph,
    *,
    threshold: float,
    asset_thresholds: Optional[Mapping[str, float]] = None,
    constraints: Optional[PlanConstraints] = None,
) -> BaselineResult:
    """Existing greedy MRC, stopped at the shortest prefix that meets the thresholds.

    If greedy never meets them (some exposure is irreducible), the full greedy plan is
    returned. For a fair comparison with ``optimize`` we then compare the cost needed to
    reach the same achieved exposure.
    """
    c = constraints or PlanConstraints()
    thresholds = {a: float((asset_thresholds or {}).get(a, threshold)) for a in twin.protected}
    t0 = time.perf_counter()
    variant = twin.with_policy(c.expire_policy)
    plan = plan_mrc(variant, budget=10_000.0, harden_factor=NARROW_FACTOR)
    actions: List[PlannedAction] = []
    exp = exposure(twin)
    if all(exp[k] <= thresholds[k] + 1e-9 for k in exp):
        return BaselineResult([], 0.0, True, exp, time.perf_counter() - t0)
    for a in plan.actions:
        meta = twin.route_meta[a.edge_id]
        if a.action == "remove":
            actions.append(PlannedAction(meta.route_id, "expire", 1.25, meta.observed_sessions_30d, c.expire_reversible))
        else:
            actions.append(PlannedAction(meta.route_id, "narrow", 1.0, 0, True))
        exp = exposure(apply_actions(twin, actions))
        if all(exp[k] <= thresholds[k] + 1e-9 for k in exp):
            return BaselineResult(actions, sum(x.cost for x in actions), True, exp, time.perf_counter() - t0)
    exp = exposure(apply_actions(twin, actions))
    return BaselineResult(actions, sum(x.cost for x in actions), False, exp, time.perf_counter() - t0)


def compare_with_greedy(twin: CyberTwinGraph, plan: BreachPathPlan,
                        constraints: Optional[PlanConstraints] = None) -> Dict[str, Any]:
    """Greedy effort to reach (at least) the exposure the exact plan achieved, per asset.

    Both plans are scored with the same objective (``plan_objective``).
    """
    target = {a: max(plan.exposure_after[a], plan.thresholds[a]) for a in plan.exposure_after}
    res = greedy_to_threshold(twin, threshold=1.0, asset_thresholds=target, constraints=constraints)
    exact_obj, greedy_obj = plan_objective(plan.actions), plan_objective(res.actions)
    return {
        "greedy_reached": res.reached,
        "exact_objective": exact_obj,
        "greedy_objective": greedy_obj,
        "exact_changes": len(plan.actions),
        "greedy_changes": len(res.actions),
        "saving_pct": round(100 * (greedy_obj - exact_obj) / greedy_obj, 1) if res.reached and greedy_obj else None,
    }


def frontier(
    twin: CyberTwinGraph,
    thresholds: Sequence[float] = (0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01),
    constraints: Optional[PlanConstraints] = None,
) -> List[Dict[str, Any]]:
    """Minimum cost against target exposure: the commander's trade-off curve."""
    rows = []
    for tau in thresholds:
        plan = optimize(twin, threshold=tau, constraints=constraints)
        rows.append({
            "threshold": tau,
            "cost": plan.total_cost,
            "changes": len(plan.actions),
            "worst_exposure_after": max(plan.exposure_after.values()) if plan.exposure_after else 0.0,
            "assets_meeting_threshold": sum(1 for a, v in plan.exposure_after.items() if v <= plan.thresholds[a] + 1e-9),
            "assets": len(plan.exposure_after),
            "status": plan.status,
        })
    return rows


# --------------------------------------------------------------------------------------
# synthetic scale twins (benchmarks only)
# --------------------------------------------------------------------------------------
SERVICES = ["https", "ssh", "smb", "rdp", "postgres", "mssql", "ldap", "kerberos", "syslog", "https-api"]


def scale_scenario(n_nodes: int, *, seed: int = 0, out_degree: float = 2.5,
                   n_protected: int = 6, required_share: float = 0.25) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Layered enterprise-like graph: footholds -> user groups -> app tiers -> data tier."""
    rng = random.Random(seed)
    tiers = [max(2, n_nodes // 8), max(4, n_nodes // 3), max(4, n_nodes // 3), max(n_protected, n_nodes // 6)]
    nodes: List[List[str]] = [["ext:internet"] + [f"grp:users-{i}" for i in range(tiers[0])]]
    nodes += [[f"srv-t{t}-{i:04d}" for i in range(tiers[t])] for t in (1, 2, 3)]
    routes, findings = [], []
    rid = 0
    for t in range(3):
        for src in nodes[t]:
            for _ in range(max(1, int(rng.expovariate(1 / out_degree)))):
                dst = rng.choice(nodes[t + 1] + (nodes[t + 2] if t + 2 < 4 and rng.random() < 0.15 else []))
                svc = rng.choice(SERVICES)
                used = 0 if rng.random() < 0.3 else int(rng.lognormvariate(5, 2))
                routes.append({
                    "id": f"rt-s{rid:05d}", "source": src, "target": dst, "service": svc, "port": 443,
                    "prefix": "10.0.0.0/8", "source_size": 1, "status": "active", "narrow_to": None,
                    "narrow_candidate": "10.0.0.0/28" if rng.random() < 0.5 else None,
                    "observed_sessions_30d": used, "sealed_tunnel": rng.random() < 0.1,
                })
                rid += 1
    for i, host in enumerate(rng.sample(nodes[2] + nodes[3], k=min(len(nodes[2]) + len(nodes[3]), n_nodes // 3))):
        findings.append({"id": f"SYN-2026-{i + 1:04d}", "host": host, "service": rng.choice(SERVICES),
                         "cvss": round(rng.uniform(4, 10), 1), "epss": round(rng.random() ** 2, 3), "kev": rng.random() < 0.1})
    protected = rng.sample(nodes[3], k=n_protected)
    required = rng.sample(routes, k=int(len(routes) * required_share))
    mission = {
        "footholds": ["ext:internet", nodes[0][1]],
        "protected_assets": {p: "synthetic crown jewel" for p in protected},
        "required_flows": [{"id": f"F-{i:04d}", "route": r["id"]} for i, r in enumerate(required)],
        "identity_edges": [],
    }
    return {"routes": routes, "vulnerabilities": findings}, mission


def scale_twin(n_nodes: int, *, seed: int = 0, n_protected: int = 6) -> CyberTwinGraph:
    """Scale twin whose protected assets are the most exposed reachable data-tier nodes."""
    scen, mission = scale_scenario(n_nodes, seed=seed, n_protected=n_protected)
    candidates = sorted({r["target"] for r in scen["routes"] if str(r["target"]).startswith("srv-t3-")})
    mission = {**mission, "protected_assets": {c: "candidate" for c in candidates}}
    twin = build_twin(scen["routes"], scen["vulnerabilities"], mission)
    ranked = sorted(exposure(twin).items(), key=lambda kv: (-kv[1], kv[0]))
    chosen = [a for a, v in ranked if v > 0][:n_protected]
    twin.set_scope(twin.footholds, chosen, [])
    return twin
