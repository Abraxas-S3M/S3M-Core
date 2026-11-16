"""QuantumWatch risk model and migration planner.

Military/tactical context:
The question a crypto authority must answer is not "what is vulnerable" (almost everything)
but "what do we fix first, with the engineers we have, to lose the least to harvest-now-
decrypt-later and still meet the profile deadlines". This module answers it.

Risk (per asset, per quarter it remains unmigrated), using the customer's CRQC CDF ``F``:
- confidentiality (quantum-breakable key agreement, or cleartext): traffic captured in
  quarter ``t`` is lost if a CRQC exists before its secrecy lifetime ``x`` ends:
  ``rate = value * capture * F(t + x) / 4`` (Mosca's inequality, integrated over time).
  ``capture`` is 1.0 for internet-facing paths, 0.5 at rest, 0.3 for internal paths.
  Cleartext is exposed today (``F = 1``);
- authenticity (quantum-breakable signatures): forgery possible once a CRQC exists,
  ``rate = value * (1 + trust_years / 10) * F(t) / 4``;
- anything not migrated in the horizon pays a 10-year tail at its last rate.

Options per asset: **native** migration (the asset's own effort; ends exposure and counts
for compliance) and, for fabric confidentiality only, an **XiiD SealedTunnel overlay**
(0.5 engineer-weeks per route; cuts capture to ``overlay_residual``; does not count for
compliance unless the profile accepts compensating controls). The overlay's PQ protection is
a vendor claim: REQUIRES XIID VALIDATION; ``overlay_residual`` is the hedge.

Plan: CP-SAT over quarters with engineer-week capacity, native-migration dependencies
(e.g. root CA before issuing CA) and profile deadlines (hard, or reported as infeasible
with the shortfall).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.cortex.quantumwatch.catalog import approved, get

VALUE = {"personnel": 3.0, "financial": 3.0, "identity": 3.0, "evidence": 2.0, "operational": 1.0,
         "telemetry": 0.3, "public": 0.0}
SCALE = 10_000


@dataclass
class PlanAsset:
    asset_id: str
    algo_id: str
    usage: str
    data_class: str = "operational"
    category: str = "custom_application"
    capture: float = 0.3
    trust_years: float = 0.0
    native_weeks: float = 2.0
    overlay_possible: bool = False
    depends_on: List[str] = field(default_factory=list)
    route_id: Optional[str] = None


class CRQC:
    def __init__(self, cdf: Mapping[Any, float]) -> None:
        pts = sorted((float(k), float(v)) for k, v in cdf.items())
        self.years = [y for y, _ in pts]
        self.p = [p for _, p in pts]

    def F(self, year: float) -> float:  # noqa: N802 - conventional name for a CDF
        if year <= self.years[0]:
            return self.p[0] * max(0.0, (year - (self.years[0] - 2)) / 2)
        if year >= self.years[-1]:
            return self.p[-1]
        i = bisect.bisect_right(self.years, year)
        y0, y1, p0, p1 = self.years[i - 1], self.years[i], self.p[i - 1], self.p[i]
        return p0 + (p1 - p0) * (year - y0) / (y1 - y0)


def needs_migration(a: PlanAsset, profile: Mapping[str, Any]) -> bool:
    algo = get(a.algo_id)
    if algo.quantum == "n/a":
        return False  # unknown crypto: investigate first, cannot be planned
    if a.usage in ("integrity", "non-security", "key-derivation") and algo.quantum != "broken_by_shor":
        return False
    return not approved(algo, profile)


def quarter_rates(a: PlanAsset, crqc: CRQC, years: Mapping[str, float], start: float, quarters: int,
                  overlay_residual: float) -> Tuple[List[float], List[float]]:
    """(full-exposure rate, overlay-residual rate) per quarter."""
    algo = get(a.algo_id)
    value = VALUE.get(a.data_class, 1.0)
    full, res = [], []
    for q in range(quarters):
        t = start + q / 4 + 0.125
        if a.usage == "authenticity" and algo.quantum == "broken_by_shor":
            r = value * (1 + a.trust_years / 10) * crqc.F(t) / 4
            full.append(r)
            res.append(r)  # an overlay does not protect signatures
        elif a.usage == "confidentiality" and algo.quantum in ("broken_by_shor", "classically_broken", "n/a"):
            f = 1.0 if algo.quantum == "classically_broken" else crqc.F(t + years.get(a.data_class, 3))
            r = value * a.capture * f / 4
            full.append(r)
            res.append(r * overlay_residual if a.overlay_possible else r)
        else:
            full.append(0.0)  # compliance-only gap (e.g. AES-128 under CNSA 2.0)
            res.append(0.0)
    return full, res


@dataclass
class MigrationPlan:
    status: str
    start_year: int
    quarters: int
    capacity_weeks: float
    native: Dict[str, int]  # asset -> quarter index (0 = first quarter)
    overlay: Dict[str, int]
    risk: float
    risk_by_asset: Dict[str, float]
    deadline_misses: Dict[str, str]
    weeks_used: List[float]

    def quarter_label(self, q: int) -> str:
        return f"{self.start_year + q // 4}Q{q % 4 + 1}"

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "risk": round(self.risk, 4), "capacity_weeks_per_quarter": self.capacity_weeks,
                "native": {k: self.quarter_label(v) for k, v in sorted(self.native.items())},
                "overlay": {k: self.quarter_label(v) for k, v in sorted(self.overlay.items())},
                "deadline_misses": self.deadline_misses,
                "weeks_used": [round(w, 2) for w in self.weeks_used]}


def span(weeks: float, capacity: float) -> int:
    """Quarters a native migration occupies (large efforts spread over half the capacity)."""
    if weeks <= capacity / 2:
        return 1
    return int(-(-weeks // (capacity / 2)))


def _deadline_quarter(a: PlanAsset, profile: Mapping[str, Any], start_year: int) -> int:
    d = profile.get("category_deadlines", {}).get(a.category) or profile["disallowed_after"]
    y, m, _ = (int(x) for x in str(d).split("-"))
    return (y - start_year) * 4 + (m - 1) // 3  # must be done by the end of this quarter


def evaluate(assets: Sequence[PlanAsset], native: Mapping[str, int], overlay: Mapping[str, int], *,
             crqc: CRQC, years: Mapping[str, float], start_year: int, quarters: int,
             overlay_residual: float) -> Dict[str, float]:
    """Risk of a given schedule (shared by the optimiser and any baseline)."""
    out = {}
    for a in assets:
        full, res = quarter_rates(a, crqc, years, start_year, quarters, overlay_residual)
        n, o = native.get(a.asset_id, quarters), overlay.get(a.asset_id, quarters)
        r = 0.0
        for q in range(quarters):
            if q > n:
                break
            r += res[q] if q > o else full[q]
        if n >= quarters:
            r += 40 * (res[-1] if o < quarters else full[-1])
        out[a.asset_id] = r
    return out


def plan(assets: Sequence[PlanAsset], profile: Mapping[str, Any], *, crqc: CRQC, years: Mapping[str, float],
         start_year: int = 2027, end_year: int = 2035, capacity_weeks: float = 12.0, overlay_weeks: float = 0.5,
         overlay_residual: float = 0.05, enforce_deadlines: bool = True, time_limit: float = 20.0) -> MigrationPlan:
    from ortools.sat.python import cp_model

    Q = (end_year - start_year + 1) * 4
    todo = [a for a in assets if needs_migration(a, profile)]
    m = cp_model.CpModel()
    n = {(a.asset_id, q): m.NewBoolVar(f"n_{a.asset_id}_{q}") for a in todo for q in range(Q)}
    o = {(a.asset_id, q): m.NewBoolVar(f"o_{a.asset_id}_{q}") for a in todo if a.overlay_possible for q in range(Q)}
    N, C = {}, {}  # done natively by (end of) quarter t; covered (native or overlay) by t
    obj = []
    for a in todo:
        aid = a.asset_id
        m.Add(sum(n[aid, q] for q in range(Q)) <= 1)
        if a.overlay_possible:
            m.Add(sum(o[aid, q] for q in range(Q)) <= 1)
        full, res = quarter_rates(a, crqc, years, start_year, Q, overlay_residual)
        for t in range(Q):
            N[aid, t] = m.NewBoolVar(f"N_{aid}_{t}")
            m.Add(N[aid, t] == sum(n[aid, q] for q in range(t + 1)))
            if a.overlay_possible:
                Ot = sum(o[aid, q] for q in range(t + 1))
                C[aid, t] = m.NewBoolVar(f"C_{aid}_{t}")
                m.Add(C[aid, t] >= N[aid, t])
                m.Add(C[aid, t] <= N[aid, t] + Ot)
                for q in range(t + 1):
                    m.AddImplication(o[aid, q], C[aid, t])
            else:
                C[aid, t] = N[aid, t]
        # Exposure in quarter t counts until the migration completes in t (inclusive).
        for t in range(Q):
            prev_n = N[aid, t - 1] if t else 0
            prev_c = C[aid, t - 1] if t else 0
            # full exposure while not covered; residual while covered by overlay but not native
            fr, rr = int(round(full[t] * SCALE)), int(round(res[t] * SCALE))
            if fr:
                obj.append(fr * (1 - prev_c))
            if rr and a.overlay_possible:
                obj.append(rr * (prev_c - prev_n))
        tail_full, tail_res = int(round(40 * full[-1] * SCALE)), int(round(40 * res[-1] * SCALE))
        obj.append(tail_full * (1 - C[aid, Q - 1]) + (tail_res * (C[aid, Q - 1] - N[aid, Q - 1]) if a.overlay_possible
                                                    else 0))
        if enforce_deadlines:
            dq = _deadline_quarter(a, profile, start_year)
            if 0 <= dq < Q:  # deadlines beyond the horizon are not constrained here
                m.Add(N[aid, dq] == 1)
    ids = {a.asset_id for a in todo}
    for a in todo:
        for parent in a.depends_on:
            if parent in ids:
                for t in range(Q):
                    m.Add(N[a.asset_id, t] <= (N[parent, t - 1] if t else 0))
    k = {a.asset_id: span(a.native_weeks, capacity_weeks) for a in todo}
    for a in todo:
        for q in range(min(Q, k[a.asset_id] - 1)):
            m.Add(n[a.asset_id, q] == 0)  # cannot finish before its span has elapsed
    for q in range(Q):
        load = []
        for a in todo:
            per = int(round(a.native_weeks * 10 / k[a.asset_id]))
            # finishing in q' occupies quarters q'-k+1 .. q'
            load += [per * n[a.asset_id, q2] for q2 in range(q, min(Q, q + k[a.asset_id]))]
        m.Add(sum(load) + sum(int(overlay_weeks * 10) * o[a.asset_id, q] for a in todo if a.overlay_possible)
              <= int(capacity_weeks * 10))
    # Tie-break: earlier is better for equal risk (small effort-time term).
    obj.append(sum(q * n[a.asset_id, q] for a in todo for q in range(Q)))
    m.Minimize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if enforce_deadlines:
            relaxed = plan(assets, profile, crqc=crqc, years=years, start_year=start_year, end_year=end_year,
                           capacity_weeks=capacity_weeks, overlay_weeks=overlay_weeks,
                           overlay_residual=overlay_residual, enforce_deadlines=False, time_limit=time_limit)
            relaxed.status = "DEADLINES_INFEASIBLE"
            return relaxed
        return MigrationPlan("INFEASIBLE", start_year, Q, capacity_weeks, {}, {}, float("inf"), {}, {}, [])
    native = {a.asset_id: q for a in todo for q in range(Q) if solver.Value(n[a.asset_id, q])}
    overlay = {a.asset_id: q for a in todo if a.overlay_possible for q in range(Q) if solver.Value(o[a.asset_id, q])}
    return _finish("OPTIMAL" if st == cp_model.OPTIMAL else "FEASIBLE", todo, native, overlay, profile, crqc, years,
                   start_year, Q, capacity_weeks, overlay_weeks, overlay_residual)


def _finish(status, todo, native, overlay, profile, crqc, years, start_year, Q, capacity_weeks, overlay_weeks,
            overlay_residual) -> MigrationPlan:
    risk = evaluate(todo, native, overlay, crqc=crqc, years=years, start_year=start_year, quarters=Q,
                    overlay_residual=overlay_residual)
    misses = {}
    for a in todo:
        dq = _deadline_quarter(a, profile, start_year)
        if native.get(a.asset_id, Q) > dq:
            misses[a.asset_id] = "not migrated" if a.asset_id not in native else f"late by {native[a.asset_id] - dq} q"
    weeks = [0.0] * Q
    for a in todo:
        if a.asset_id in native:
            k = span(a.native_weeks, capacity_weeks)
            for q in range(max(0, native[a.asset_id] - k + 1), native[a.asset_id] + 1):
                weeks[q] += a.native_weeks / k
        if a.asset_id in overlay:
            weeks[overlay[a.asset_id]] += overlay_weeks
    return MigrationPlan(status, start_year, Q, capacity_weeks, native, overlay, sum(risk.values()), risk, misses, weeks)


def baseline_plan(assets: Sequence[PlanAsset], profile: Mapping[str, Any], *, crqc: CRQC,
                  years: Mapping[str, float], start_year: int = 2027, end_year: int = 2035,
                  capacity_weeks: float = 12.0, overlay_residual: float = 0.05) -> MigrationPlan:
    """Common practice: native only, earliest deadline first, then highest current risk; respects dependencies."""
    Q = (end_year - start_year + 1) * 4
    todo = [a for a in assets if needs_migration(a, profile)]
    rate0 = {a.asset_id: quarter_rates(a, crqc, years, start_year, Q, overlay_residual)[0][0] for a in todo}
    order = sorted(todo, key=lambda a: (_deadline_quarter(a, profile, start_year), -rate0[a.asset_id], a.asset_id))
    native: Dict[str, int] = {}
    used = [0.0] * Q
    pending = list(order)
    for q in range(Q):
        for a in list(pending):
            if any(p not in native or native[p] >= q for p in a.depends_on if p in rate0):
                continue
            k = span(a.native_weeks, capacity_weeks)
            qs = range(q, q + k)
            if q + k - 1 < Q and all(used[x] + a.native_weeks / k <= capacity_weeks + 1e-9 for x in qs):
                native[a.asset_id] = q + k - 1
                for x in qs:
                    used[x] += a.native_weeks / k
                pending.remove(a)
    return _finish("HEURISTIC", todo, native, {}, profile, crqc, years, start_year, Q, capacity_weeks, 0.5,
                   overlay_residual)


def today_year() -> float:
    d = date.today()
    return d.year + (d.timetuple().tm_yday - 1) / 365.0


__all__ = ["CRQC", "MigrationPlan", "PlanAsset", "baseline_plan", "evaluate", "needs_migration", "plan",
           "quarter_rates", "span"]
