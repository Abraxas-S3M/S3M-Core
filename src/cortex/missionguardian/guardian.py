"""MissionGuardian: mission continuity, OT safety and change windows as hard constraints.

Military/tactical context:
"Don't break the mission" cannot be an optimisation weight that a large enough risk
reduction outbids. MissionGuardian turns the mission owner's rules into three things:

* ``compile_constraints`` - limits every planner must obey right now (BreachPath
  ``PlanConstraints``: forbidden actions, caps). Changes outside their window are not
  forbidden forever; they are forbidden *now* and handed to the scheduler.
* ``validate`` - an independent check of any finished plan, from any planner, returning
  each violated rule by id. The defense cycle refuses to authorise a plan that fails it.
* ``schedule`` - the earliest compliant window for each change, honouring tier windows,
  freezes and per-segment concurrency (OR-Tools CP-SAT; exact for the plan sizes used).

Every rule carries an id so a refusal can be traced to the line of policy that caused it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

import yaml

from src.cortex.cybertwin import CyberTwinGraph

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True)
class Window:
    days: Tuple[str, ...]
    start: str
    end: str

    def occurrences(self, after: datetime, horizon_days: int = 14) -> List[Tuple[datetime, datetime]]:
        """Concrete [start, end) intervals overlapping [after, after + horizon)."""
        out = []
        base = after.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        sh, sm = map(int, self.start.split(":"))
        eh, em = map(int, self.end.split(":"))
        for d in range(horizon_days + 2):
            day = base + timedelta(days=d)
            if DAYS[day.weekday()] not in self.days:
                continue
            s = day.replace(hour=sh, minute=sm)
            e = day.replace(hour=eh, minute=em)
            if e <= s:
                e += timedelta(days=1)  # wraps midnight
            if e > after:
                out.append((max(s, after), e))
        return out


@dataclass
class Mission:
    mission_id: str
    tier: int
    flows: List[str]
    assets: List[str]
    description: str = ""


@dataclass
class Violation:
    rule_id: str
    route_id: Optional[str]
    message: str


@dataclass
class MissionPolicy:
    timezone: ZoneInfo
    missions: List[Mission]
    windows: Dict[int, List[Window]]
    rules: List[Dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> "MissionPolicy":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            timezone=ZoneInfo(raw.get("timezone", "UTC")),
            missions=[Mission(m["id"], int(m["tier"]), list(m.get("flows", [])), list(m.get("assets", [])),
                              m.get("description", "")) for m in raw.get("missions", [])],
            windows={int(t): [Window(tuple(w["days"]), w["start"], w["end"]) for w in ws]
                     for t, ws in (raw.get("change_windows") or {}).items()},
            rules=list(raw.get("rules", [])),
        )

    def rules_of(self, kind: str) -> List[Dict[str, Any]]:
        return [r for r in self.rules if r.get("kind") == kind]


@dataclass
class RouteContext:
    route_id: str
    tier: Optional[int]
    missions: List[str]
    segment: str
    protected_by: List[str] = field(default_factory=list)


class MissionGuardian:
    def __init__(self, policy: MissionPolicy, twin: CyberTwinGraph,
                 segments: Optional[Mapping[str, str]] = None) -> None:
        self.policy = policy
        self.twin = twin
        self.segments = dict(segments or {})
        self.context: Dict[str, RouteContext] = {}
        flow_to_mission: Dict[str, Mission] = {f: m for m in policy.missions for f in m.flows}
        asset_to_missions: Dict[str, List[Mission]] = {}
        for m in policy.missions:
            for a in m.assets:
                asset_to_missions.setdefault(a, []).append(m)
        protected = {t: r["id"] for r in policy.rules_of("protected_routes") for t in r.get("targets", [])}
        for meta in twin.route_meta.values():
            ms: Dict[str, Mission] = {}
            for f in meta.required_by:
                if f in flow_to_mission:
                    ms[flow_to_mission[f].mission_id] = flow_to_mission[f]
            for m in asset_to_missions.get(meta.target, []):
                ms[m.mission_id] = m
            tier = min((m.tier for m in ms.values()), default=None)
            self.context[meta.route_id] = RouteContext(
                route_id=meta.route_id, tier=tier, missions=sorted(ms),
                segment=self.segments.get(meta.target, meta.target),
                protected_by=[protected[meta.target]] if meta.target in protected else [],
            )

    # ---- time ----------------------------------------------------------------------
    def _local(self, now: datetime) -> datetime:
        return now.astimezone(self.policy.timezone).replace(tzinfo=None)

    def window_open(self, route_id: str, now: datetime) -> bool:
        tier = self.context[route_id].tier
        if tier is None or tier not in self.policy.windows:
            return True
        local = self._local(now)
        return any(s <= local < e for w in self.policy.windows[tier] for s, e in w.occurrences(local, 2))

    def active_freezes(self, now: datetime) -> List[Dict[str, Any]]:
        return [r for r in self.policy.rules_of("freeze")
                if datetime.fromisoformat(r["start"]) <= now < datetime.fromisoformat(r["end"])]

    # ---- compile -------------------------------------------------------------------
    def compile_constraints(self, now: datetime, *, expire_policy: str = "unused_only",
                            expire_reversible: bool = False, ignore_windows: bool = False):
        from src.cortex.breachpath.optimizer import PlanConstraints

        forbidden: Dict[str, Set[str]] = {}
        for rid, ctx in self.context.items():
            if ctx.protected_by or (not ignore_windows and not self.window_open(rid, now)):
                forbidden[rid] = {"narrow", "expire"}
        caps = [int(r["max"]) for r in self.policy.rules_of("max_changes")]
        max_irrev = None
        for f in ([] if ignore_windows else self.active_freezes(now)):
            caps.append(int(f.get("max_changes", 0)))
            if not f.get("allow_irreversible", True):
                max_irrev = 0
        tier_caps = (self.policy.rules_of("disruption_cap") or [{}])[0].get("caps", {})
        # Expiring a route touching tier t may cut at most cap[t] sessions: forbid beyond that.
        for rid, ctx in self.context.items():
            cap = tier_caps.get(ctx.tier if ctx.tier is not None else "untiered")
            meta = self.twin.route_meta[self.twin.route_edge[rid]]
            if cap is not None and meta.observed_sessions_30d > int(cap):
                forbidden.setdefault(rid, set()).add("expire")
        return PlanConstraints(
            forbidden=forbidden,
            expire_policy=expire_policy,
            expire_reversible=expire_reversible,
            max_changes=min(caps) if caps else None,
            max_irreversible=max_irrev,
        )

    # ---- validate ------------------------------------------------------------------
    def validate(self, changes: Sequence[Mapping[str, Any]], now: datetime, *,
                 require_window: bool = True) -> List[Violation]:
        """Check a finished plan. ``changes``: dicts with route_id, xiid_action, reversible."""
        v: List[Violation] = []
        tier_caps = (self.policy.rules_of("disruption_cap") or [{}])[0]
        per_segment: Dict[str, int] = {}
        for ch in changes:
            rid = str(ch["route_id"])
            ctx = self.context.get(rid)
            if ctx is None:
                v.append(Violation("R-UNKNOWN-ROUTE", rid, "route not in twin"))
                continue
            for rule in ctx.protected_by:
                v.append(Violation(rule, rid, f"route reaches protected asset ({ctx.segment})"))
            if require_window and not self.window_open(rid, now):
                v.append(Violation(f"W-TIER-{ctx.tier}", rid, "outside the change window for its mission tier"))
            meta = self.twin.route_meta[self.twin.route_edge[rid]]
            if meta.required_by and ch.get("xiid_action") == "expire_route":
                v.append(Violation("R-REQUIRED-FLOW", rid, f"would break {', '.join(meta.required_by)}"))
            cap = tier_caps.get("caps", {}).get(ctx.tier if ctx.tier is not None else "untiered")
            if cap is not None and ch.get("xiid_action") == "expire_route" and meta.observed_sessions_30d > int(cap):
                v.append(Violation(tier_caps["id"], rid, f"cuts {meta.observed_sessions_30d} sessions; tier cap {cap}"))
            per_segment[ctx.segment] = per_segment.get(ctx.segment, 0) + 1
        for rule in self.policy.rules_of("concurrency"):
            for seg, count in per_segment.items():
                if count > int(rule["max_per_segment"]):
                    v.append(Violation(rule["id"], None, f"{count} changes on {seg} in one window"))
        for rule in self.policy.rules_of("max_changes"):
            if len(changes) > int(rule["max"]):
                v.append(Violation(rule["id"], None, f"{len(changes)} changes > {rule['max']}"))
        for f in self.active_freezes(now):
            if len(changes) > int(f.get("max_changes", 0)):
                v.append(Violation(f["id"], None, f"freeze allows {f.get('max_changes', 0)} changes"))
            if not f.get("allow_irreversible", True) and any(not c.get("reversible", True) for c in changes):
                v.append(Violation(f["id"], None, "freeze forbids irreversible changes"))
        return v

    # ---- schedule ------------------------------------------------------------------
    def schedule(self, changes: Sequence[Mapping[str, Any]], now: datetime,
                 horizon_days: int = 14) -> Dict[str, Any]:
        """Earliest compliant window per change (CP-SAT): tier windows + segment concurrency."""
        from ortools.sat.python import cp_model

        local_now = self._local(now)
        slots: List[Tuple[datetime, datetime]] = []
        for ws in self.policy.windows.values():
            for w in ws:
                slots.extend(w.occurrences(local_now, horizon_days))
        slots.append((local_now, local_now + timedelta(hours=1)))  # "now" slot for untiered routes
        slots = sorted(set(slots))
        concurrency = int((self.policy.rules_of("concurrency") or [{"max_per_segment": 99}])[0]["max_per_segment"])

        def fits(rid: str, slot: Tuple[datetime, datetime]) -> bool:
            ctx = self.context[rid]
            if ctx.protected_by:
                return False
            if ctx.tier is None or ctx.tier not in self.policy.windows:
                return True
            return any(s <= slot[0] < e for w in self.policy.windows[ctx.tier] for s, e in w.occurrences(slot[0], 1))

        m = cp_model.CpModel()
        assign: Dict[Tuple[int, int], Any] = {}
        unschedulable = []
        for i, ch in enumerate(changes):
            options = [j for j, s in enumerate(slots) if fits(str(ch["route_id"]), s)]
            if not options:
                unschedulable.append(str(ch["route_id"]))
                continue
            for j in options:
                assign[(i, j)] = m.NewBoolVar(f"a_{i}_{j}")
            m.AddExactlyOne(assign[(i, j)] for j in options)
        for j in range(len(slots)):
            by_seg: Dict[str, List[Any]] = {}
            for (i, jj), var in assign.items():
                if jj == j:
                    by_seg.setdefault(self.context[str(changes[i]["route_id"])].segment, []).append(var)
            for vs in by_seg.values():
                m.Add(sum(vs) <= concurrency)
        m.Minimize(sum(j * var for (i, j), var in assign.items()))
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        status = solver.Solve(m)
        plan: Dict[str, str] = {}
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (i, j), var in assign.items():
                if solver.Value(var):
                    plan[str(changes[i]["route_id"])] = slots[j][0].isoformat(timespec="minutes")
        return {"slots": plan, "unschedulable": unschedulable, "timezone": str(self.policy.timezone),
                "status": solver.StatusName(status)}
