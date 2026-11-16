"""GhostShift: bounded moving-target defence on approved paths (capability 02).

Military/tactical context:
An adversary who has mapped the fabric holds *knowledge*: an STLink credential lifted from
a host, the key material of a tunnel. Rotating that secret makes the knowledge worthless,
but every rotation is a change, and the blueprint is explicit: unnecessary reconfiguration
is not a benefit. GhostShift rotates only what matters, as often as it is worth it, inside
the change windows, never changing reachability.

Model (per secret ``i``: an STLink identity or a SealedTunnel key):
- **importance** ``w_i``: the rise in mission exposure on the CyberTwin if the secret were in
  adversary hands (its sealed routes lose their SealedTunnel factor). Zero means the secret
  protects nothing that matters and it is never rotated;
- **acquisition rate** ``a_i``: base rate for the secret's kind times how reachable its host is
  from the footholds (an adversary must reach a host to steal from it);
- with Poisson acquisition and ``n`` evenly spaced rotations over horizon ``H``, the expected
  time an adversary holds a valid secret is ``(n+1) * g(H/(n+1))`` with
  ``g(L) = L - (1 - exp(-a L)) / a``, convex decreasing in ``n``;
- **allocation**: choose ``n_i`` (CP-SAT multiple-choice knapsack) minimising
  ``sum w_i * exposure_i(n_i) + lambda * disruption_i * n_i`` subject to a rotation budget
  (stability) and a minimum interval between rotations of the same secret;
- **schedule**: place rotations in MissionGuardian windows for the tier the secret serves,
  with a per-window cap; protected targets are planned but marked manual-only;
- **event trigger**: on evidence a secret is compromised, rotate it in the next window;
- **execution**: same approvals, broker and receipts as every change; postconditions check
  the epoch moved, that reachability is unchanged, and that every mission flow is still
  healthy (AutoHeal probes). Any failure stops the remaining rotations.

The rotation tools are PROPOSED contract extensions (``stlink.rotate_identity``,
``tunnel.rekey``), implemented only in the range: REQUIRES XIID VALIDATION.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.cortex.architect import ProposedChange
from src.cortex.cybertwin import MAX_P, SEALED_FACTOR, build_twin

BASE_RATE_PER_DAY = {"stlink": 1 / 180, "tunnel": 1 / 365}
DISRUPTION = {"stlink": 1.0, "tunnel": 0.2}  # relative operational cost of one rotation


@dataclass
class Secret:
    secret_id: str
    kind: str  # stlink | tunnel
    host: str
    routes: List[str]
    importance: float = 0.0
    rate_per_day: float = 0.0
    tier: Optional[int] = None
    manual_only: bool = False
    rotations: int = 0
    times: List[str] = field(default_factory=list)


def _mission_exposure(routes, findings, mission) -> float:
    twin = build_twin(routes, findings, mission)
    return sum(max((twin.max_path_prob(f, a) for f in twin.footholds), default=0.0) for a in twin.protected)


def inventory(routes: Sequence[Mapping[str, Any]], stlinks: Sequence[Mapping[str, Any]],
              findings: Sequence[Mapping[str, Any]], mission: Mapping[str, Any], *, guard=None,
              protected_targets: Sequence[str] = ()) -> List[Secret]:
    """Secrets with their importance and acquisition rate.

    Importance is *path-specific*: for each sealed route the secret protects,
    ``reach(source) * (p_unsealed - p_sealed) * sum_a P(target -> a)``, i.e. how much more
    likely the paths through that route become if the secret is stolen. The network-wide
    max-path exposure is deliberately not used: it hides defence-in-depth value whenever a
    weaker parallel path exists, which is exactly when BreachPath is about to close it.
    """
    twin = build_twin(routes, findings, mission)
    sealed = [r for r in routes if r.get("sealed_tunnel") and r.get("status") != "expired"]

    def reach(node: str) -> float:
        if node in twin.footholds:
            return 1.0
        if node not in twin.nodes:
            return 0.0
        return max((twin.max_path_prob(f, node) for f in twin.footholds), default=0.0)

    def onward(node: str) -> float:
        return sum(1.0 if a == node else twin.max_path_prob(node, a) for a in twin.protected)

    def route_importance(r: Mapping[str, Any]) -> float:
        e = twin.edges[twin.route_edge[r["id"]]]
        p_s = e.effective_p
        p_u = min(MAX_P, p_s / SEALED_FACTOR)
        return reach(str(r["source"])) * (p_u - p_s) * onward(str(r["target"]))

    imp = {r["id"]: route_importance(r) for r in sealed}

    def tier_of(rids: Sequence[str]) -> Optional[int]:
        if guard is None:
            return None
        tiers = [guard.context[r].tier for r in rids if r in guard.context and guard.context[r].tier is not None]
        return min(tiers) if tiers else None

    out = []
    for st in stlinks:
        host = str(st.get("host"))
        rids = [r["id"] for r in sealed if r["target"] == host]
        out.append(Secret(st["id"], "stlink", host, rids, sum(imp[r] for r in rids),
                          BASE_RATE_PER_DAY["stlink"] * max(0.05, reach(host)), tier_of(rids), host in protected_targets))
    for r in sealed:
        out.append(Secret("st-" + r["id"].removeprefix("rt-"), "tunnel", str(r["target"]), [r["id"]], imp[r["id"]],
                          BASE_RATE_PER_DAY["tunnel"] * max(0.05, reach(str(r["target"]))), tier_of([r["id"]]),
                          r["target"] in protected_targets))
    return sorted(out, key=lambda x: x.secret_id)


def held_time(rate: float, horizon: float, rotations: int) -> float:
    """Expected time a valid secret is in adversary hands (Poisson acquisition, even spacing)."""
    if rate <= 0:
        return 0.0
    L = horizon / (rotations + 1)
    return (rotations + 1) * (L - (1 - math.exp(-rate * L)) / rate)


@dataclass
class Allocation:
    rotations: Dict[str, int]
    objective: float
    exposure: float  # sum w_i * held_time_i
    disruption: float
    status: str


def allocate(secrets: Sequence[Secret], *, horizon_days: float = 90, budget: int = 20, min_interval_days: float = 7,
             disruption_weight: float = 0.002) -> Allocation:
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    choose, cost_terms, exp_tab, dis_tab = {}, [], {}, {}
    max_n = max(0, int(horizon_days // min_interval_days) - 1)
    for s in secrets:
        opts = range(0, max_n + 1 if s.importance > 0 else 1)  # unimportant secrets: never rotate
        vars_ = []
        for n in opts:
            v = m.NewBoolVar(f"{s.secret_id}_{n}")
            choose[s.secret_id, n] = v
            e = s.importance * held_time(s.rate_per_day, horizon_days, n)
            d = disruption_weight * DISRUPTION[s.kind] * n
            exp_tab[s.secret_id, n], dis_tab[s.secret_id, n] = e, d
            cost_terms.append(int(round((e + d) * 1e6)) * v)
            vars_.append(v)
        m.AddExactlyOne(vars_)
    m.Add(sum(n * v for (sid, n), v in choose.items()) <= budget)
    m.Minimize(sum(cost_terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    st = solver.Solve(m)
    rot = {sid: n for (sid, n), v in choose.items() if solver.Value(v)}
    exp = sum(exp_tab[sid, n] for sid, n in rot.items())
    dis = sum(dis_tab[sid, n] for sid, n in rot.items())
    return Allocation(rot, exp + dis, exp, dis, "OPTIMAL" if st == cp_model.OPTIMAL else "FEASIBLE")


def uniform_allocation(secrets: Sequence[Secret], *, horizon_days: float = 90, budget: int = 20,
                       disruption_weight: float = 0.002) -> Allocation:
    """Common practice: the same rotation period for every secret (budget split evenly)."""
    n = budget // max(1, len(secrets))
    rem = budget - n * len(secrets)
    rot = {s.secret_id: n + (1 if i < rem else 0) for i, s in enumerate(secrets)}
    exp = sum(s.importance * held_time(s.rate_per_day, horizon_days, rot[s.secret_id]) for s in secrets)
    dis = sum(disruption_weight * DISRUPTION[s.kind] * rot[s.secret_id] for s in secrets)
    return Allocation(rot, exp + dis, exp, dis, "HEURISTIC")


def schedule(secrets: Sequence[Secret], alloc: Allocation, *, start: datetime, horizon_days: int = 90,
             guard=None, per_window_cap: int = 3) -> Dict[str, List[datetime]]:
    """Ideal even spacing, snapped to the earliest allowed window at or after each ideal time."""
    used: Dict[datetime, int] = {}
    out: Dict[str, List[datetime]] = {}
    for s in sorted(secrets, key=lambda x: -x.importance):
        n = alloc.rotations.get(s.secret_id, 0)
        if n == 0:
            continue
        windows = _windows(guard, s.tier, start, horizon_days)
        base = guard._local(start) if guard is not None else start  # noqa: SLF001 - same clock as windows
        times = []
        for k in range(1, n + 1):
            ideal = base + timedelta(days=horizon_days * k / (n + 1))
            for w in windows:
                if w >= ideal and used.get(w, 0) < per_window_cap and (not times or w > times[-1]):
                    used[w] = used.get(w, 0) + 1
                    times.append(w)
                    break
        out[s.secret_id] = times
        s.rotations, s.times = len(times), [t.isoformat() for t in times]
    return out


def _windows(guard, tier: Optional[int], start: datetime, horizon_days: int) -> List[datetime]:
    if guard is None or tier is None or tier not in guard.policy.windows:
        local = guard._local(start) if guard is not None else start  # noqa: SLF001
        return [(local + timedelta(days=d)).replace(hour=2, minute=0, second=0, microsecond=0)
                for d in range(horizon_days + 1)]
    local = guard._local(start)  # noqa: SLF001 - windows are defined in local time
    return sorted({s for w in guard.policy.windows[tier] for s, _ in w.occurrences(local, horizon_days)})


def triggered(secrets: Sequence[Secret], evidence: Mapping[str, Any]) -> List[Secret]:
    """Secrets implicated by compromise evidence (a host, a route or an explicit secret id)."""
    hosts = set(evidence.get("hosts", []))
    routes = set(evidence.get("routes", []))
    ids = set(evidence.get("secrets", []))
    return [s for s in secrets if s.secret_id in ids or s.host in hosts or routes & set(s.routes)]


def rotation_change(s: Secret, *, grace_seconds: int = 0) -> ProposedChange:
    if s.kind == "stlink":
        action, args = "rotate_stlink_identity", {"stlink_id": s.secret_id, "grace_seconds": grace_seconds}
    else:
        action, args = "rekey_tunnel", {"tunnel_id": s.secret_id}
    return ProposedChange(
        change_id=f"ghostshift-{s.secret_id}", route_id=(s.routes[0] if s.routes else s.secret_id),
        twin_action="rotate", xiid_action=action, arguments=args, rollback_action=None, rollback_arguments=None,
        reversible=False, risk_before=s.importance, risk_after=0.0, cost=DISRUPTION[s.kind],
        disrupted_sessions_30d=0, rationale=f"GhostShift: invalidate adversary knowledge of {s.secret_id} "
        f"(importance {s.importance:.4f}, acquisition {s.rate_per_day:.5f}/day)",
        expected_postcondition={"secret_id": s.secret_id, "kind": s.kind})


@dataclass
class DrillReport:
    rotated: List[Dict[str, Any]] = field(default_factory=list)
    skipped_manual: List[str] = field(default_factory=list)
    stopped: Optional[str] = None
    routes_unchanged: bool = True
    exposure_before: float = 0.0
    exposure_after: float = 0.0
    continuity: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def execute(secrets: Sequence[Secret], *, cycle, case_id: str, findings, healer=None) -> DrillReport:
    """Rotate now (a drill or an event trigger). Stops at the first failed postcondition."""
    b = cycle.broker
    await b.connect_and_pin_manifest()
    rep = DrillReport()
    routes0 = (await b.invoke("list_routes")).result["routes"]
    rep.exposure_before = round(_mission_exposure(routes0, findings, cycle.mission), 6)
    for s in secrets:
        if s.manual_only:
            rep.skipped_manual.append(s.secret_id)
            continue
        before = await _epoch(b, s)
        ch = rotation_change(s)
        auth = cycle._authorize(case_id, ch)  # noqa: SLF001 - same approval path as every change
        if not auth.get("gate_satisfied"):
            rep.stopped = f"{s.secret_id}: approval not satisfied"
            break
        await b.invoke(ch.xiid_action, ch.arguments, envelope=auth["write_envelope"],
                       idempotency_key=f"{case_id}:{ch.change_id}")
        after = await _epoch(b, s)
        ok = after == before + 1
        rep.rotated.append({"secret": s.secret_id, "kind": s.kind, "epoch": [before, after],
                            "approvals": len(auth.get("votes", [])), "postcondition": ok})
        if not ok:
            rep.stopped = f"{s.secret_id}: epoch did not advance (postcondition failed)"
            break
    routes1 = (await b.invoke("list_routes")).result["routes"]
    key = lambda rs: {r["id"]: (r.get("status"), r.get("prefix"), r.get("narrow_to"), r.get("sealed_tunnel"))  # noqa: E731
                      for r in rs}
    rep.routes_unchanged = key(routes0) == key(routes1)
    rep.exposure_after = round(_mission_exposure(routes1, findings, cycle.mission), 6)
    if healer is not None:
        rep.continuity = (await healer.run(f"{case_id}-continuity")).state
    return rep


async def _epoch(broker, s: Secret) -> int:
    if s.kind == "stlink":
        items = (await broker.invoke("list_stlinks")).result["stlinks"]
        return int(next(x for x in items if x["id"] == s.secret_id).get("identity_epoch", 0))
    items = (await broker.invoke("list_tunnels")).result["tunnels"]
    return int(next(x for x in items if x["id"] == s.secret_id).get("key_epoch", 0))


__all__ = ["Allocation", "DrillReport", "Secret", "allocate", "execute", "held_time", "inventory", "rotation_change",
           "schedule", "triggered", "uniform_allocation"]

