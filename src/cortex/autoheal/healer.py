"""AutoHeal: verified self-repair of the zero-trust fabric (capability 03).

Military/tactical context:
When the fabric degrades - an STLink drops, a route is changed outside Cortex, or traffic
silently stops while every component reports healthy - AutoHeal restores the *approved*
state, never something new, and never more exposed than the approved baseline.

Pipeline (one incident, driven by ``IncidentFSM``):

1. **Detect** (fresh MCP observation)
   - drift: a route's state differs from the approved baseline;
   - down: an STLink reports anything but ``active``;
   - symptoms: each required mission flow is a probe. Zero sessions in the last hour
     where the baseline predicts >= ``min_expected`` (Poisson P(0) <= e^-5 ~ 0.7%) is a
     failed probe; any traffic is a healthy probe; otherwise inconclusive.
2. **Localise** hidden faults: failed probes not explained by a direct fault are covered
   by a minimum set of components (CP-SAT hitting set) excluding any component on a healthy
   probe. A symptom with no candidate is escalated, never guessed.
3. **Plan** repairs that restore baseline state; reject any plan whose simulated exposure
   exceeds the approved baseline; protected routes (MissionGuardian) are escalated, not
   auto-repaired; order by the mission tier of affected flows.
4. **Authorise** each repair through the same device approvals and approval tokens as the
   defense cycle (restoration is not a free pass).
5. **Repair → verify** each step from observation; finally re-run every probe.
6. **Roll back** applied repairs on failure (where an inverse exists) and escalate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.cortex.architect import ProposedChange
from src.cortex.autoheal.fsm import IncidentFSM
from src.cortex.cybertwin import build_twin
from src.cortex.defense_cycle import DefenseCycle
from src.cortex.mcp_contract.telemetry import WINDOW, _diurnal

MIN_EXPECTED_SESSIONS = 5.0


@dataclass
class Fault:
    fault_id: str
    kind: str  # route_drift | unauthorized_route | stlink_down | silent_component
    component: str  # route:<id> | stlink:<id> | tunnel:<id>
    evidence: Dict[str, Any]
    affected_flows: List[str] = field(default_factory=list)
    tier: Optional[int] = None


@dataclass
class Probe:
    flow_id: str
    route_id: str
    expected_sessions: float
    observed_sessions: int
    components: List[str]
    verdict: str  # failed | healthy | inconclusive


@dataclass
class Repair:
    fault_id: str
    change: ProposedChange
    tier: Optional[int]


@dataclass
class IncidentReport:
    incident_id: str
    state: str
    faults: List[Dict[str, Any]] = field(default_factory=list)
    probes: List[Dict[str, Any]] = field(default_factory=list)
    repairs: List[Dict[str, Any]] = field(default_factory=list)
    escalations: List[Dict[str, Any]] = field(default_factory=list)
    exposure: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, str]] = field(default_factory=list)
    probes_after: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutoHeal:
    def __init__(
        self,
        *,
        cycle: DefenseCycle,
        baseline_routes: Mapping[str, Mapping[str, Any]],
        baseline_stlinks: Mapping[str, Mapping[str, Any]],
        min_expected: float = MIN_EXPECTED_SESSIONS,
    ) -> None:
        """``cycle`` supplies broker, approvals, mission, mission guard and clock."""
        self.cycle = cycle
        self.baseline_routes = {k: dict(v) for k, v in baseline_routes.items()}
        self.baseline_stlinks = {k: dict(v) for k, v in baseline_stlinks.items()}
        self.min_expected = min_expected
        self.flow_route = {str(f["id"]): str(f["route"]) for f in cycle.mission.get("required_flows", [])}

    # ---- observation -------------------------------------------------------------
    async def _observe(self) -> Dict[str, Any]:
        b = self.cycle.broker
        now = self.cycle.clock().astimezone(timezone.utc)  # telemetry and duty model are UTC
        routes = (await b.invoke("list_routes")).result["routes"]
        stlinks = (await b.invoke("list_stlinks")).result["stlinks"]
        since = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        until = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        windows = (await b.invoke("telemetry_flows", {"since": since, "until": until, "limit": 1000})).result["windows"]
        return {"routes": routes, "stlinks": stlinks, "windows": windows, "now": now}

    def _components(self, route: Mapping[str, Any], stlinks: Sequence[Mapping[str, Any]]) -> List[str]:
        comps = [f"route:{route['id']}"]
        if route.get("sealed_tunnel"):
            comps.append(f"tunnel:st-{str(route['id']).removeprefix('rt-')}")
            comps += [f"stlink:{s['id']}" for s in stlinks if s.get("host") == route.get("target")]
        return comps

    def _probes(self, obs: Mapping[str, Any]) -> List[Probe]:
        routes = {r["id"]: r for r in obs["routes"]}
        sessions: Dict[str, int] = {}
        starts: Dict[str, List[str]] = {}
        for w in obs["windows"]:
            sessions[w["s3m.route.id"]] = sessions.get(w["s3m.route.id"], 0) + int(w["s3m.sessions"])
            starts.setdefault(w["s3m.route.id"], []).append(w["s3m.window.start"])
        probes = []
        now = obs["now"]
        for flow, rid in sorted(self.flow_route.items()):
            base = self.baseline_routes.get(rid)
            if base is None or base.get("status") == "expired" or rid not in routes:
                continue
            per_window = int(base.get("observed_sessions_30d", 0)) / (30 * 24 * 12)
            expected = sum(per_window * _diurnal(now - timedelta(seconds=WINDOW * k)) / 0.35 for k in range(1, 13))
            observed = sessions.get(rid, 0)
            verdict = "healthy" if observed > 0 else ("failed" if expected >= self.min_expected else "inconclusive")
            probes.append(Probe(flow, rid, round(expected, 2), observed, self._components(routes[rid], obs["stlinks"]),
                                verdict))
        return probes

    def _direct_faults(self, obs: Mapping[str, Any]) -> List[Fault]:
        faults = []
        for r in obs["routes"]:
            base = self.baseline_routes.get(r["id"])
            if base is None:
                continue
            if (r.get("status"), r.get("narrow_to")) != (base.get("status"), base.get("narrow_to")):
                kind = "unauthorized_route" if base.get("status") == "expired" else "route_drift"
                faults.append(Fault(f"F-{r['id']}", kind, f"route:{r['id']}",
                                    {"observed": {"status": r.get("status"), "narrow_to": r.get("narrow_to")},
                                     "baseline": {"status": base.get("status"), "narrow_to": base.get("narrow_to")}}))
        for s in obs["stlinks"]:
            if s.get("status") != "active" and self.baseline_stlinks.get(s["id"], {}).get("status") == "active":
                faults.append(Fault(f"F-{s['id']}", "stlink_down", f"stlink:{s['id']}", {"observed": s.get("status")}))
        return faults

    def _localize(self, probes: Sequence[Probe], direct: Sequence[Fault]) -> Tuple[List[Fault], List[str]]:
        """Minimum hidden-component set explaining unexplained failed probes."""
        from ortools.sat.python import cp_model

        known = {f.component for f in direct}
        exonerated = {c for p in probes if p.verdict == "healthy" for c in p.components}
        unexplained = [p for p in probes if p.verdict == "failed" and not known & set(p.components)]
        if not unexplained:
            return [], []
        candidates = sorted({c for p in unexplained for c in p.components} - exonerated)
        orphan = [p.flow_id for p in unexplained if not set(p.components) - exonerated]
        m = cp_model.CpModel()
        x = {c: m.NewBoolVar(c) for c in candidates}
        for p in unexplained:
            cs = [x[c] for c in p.components if c in x]
            if cs:
                m.AddBoolOr(cs)
        # Fewest components that explain every failed probe; on ties prefer shared
        # infrastructure (one STLink) over per-route parts, which is what Occam suggests.
        m.Minimize(sum((10 if c.startswith("stlink:") else 11) * v for c, v in x.items()))
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.Solve(m)
        chosen = [c for c, v in x.items() if solver.Value(v)]
        faults = []
        for c in chosen:
            flows = [p.flow_id for p in unexplained if c in p.components]
            faults.append(Fault(f"F-{c.split(':', 1)[1]}", "silent_component", c,
                                {"failed_probes": flows, "exonerated_by_healthy_probes": False}, affected_flows=flows))
        return faults, orphan

    # ---- planning ------------------------------------------------------------------
    def _repair_for(self, fault: Fault, obs: Mapping[str, Any]) -> Optional[ProposedChange]:
        kind, ident = fault.component.split(":", 1)
        if kind == "route":
            base = self.baseline_routes[ident]
            obs_route = next(r for r in obs["routes"] if r["id"] == ident)
            if base.get("status") == "expired":
                action, args, inverse = "expire_route", {"route_id": ident}, None
            elif base.get("narrow_to"):
                action, args = "narrow_route", {"route_id": ident, "prefix": base["narrow_to"]}
                inverse = None
            else:
                action, args, inverse = "restore_route", {"route_id": ident}, None
            expected = {"route_id": ident, "status": base.get("status"), "narrow_to": base.get("narrow_to")}
            prior = {"status": obs_route.get("status"), "narrow_to": obs_route.get("narrow_to")}
        elif kind == "stlink" and fault.kind == "stlink_down":
            action, args, inverse = "enable_stlink", {"stlink_id": ident}, None
            expected, prior = {"stlink_id": ident, "status": "active"}, {}
        elif kind == "stlink":
            stl = next(s for s in obs["stlinks"] if s["id"] == ident)
            action, args, inverse = "deploy_stlink", {"stlink_id": ident, "endpoint": stl["endpoint"]}, None
            expected, prior = {"stlink_id": ident, "status": "active"}, {}
        else:
            return None  # e.g. a single tunnel: no contract tool repairs it directly
        return ProposedChange(
            change_id=f"heal-{fault.fault_id}", route_id=ident, twin_action="restore", xiid_action=action,
            arguments=args, rollback_action=inverse, rollback_arguments=None, reversible=True,
            risk_before=0.0, risk_after=0.0, cost=1.0, disrupted_sessions_30d=0,
            rationale=f"AutoHeal: restore approved state for {fault.component} ({fault.kind}); prior {prior}",
            expected_postcondition=expected,
        )

    def _exposure_check(self, obs: Mapping[str, Any], repairs: Sequence[Repair]) -> Dict[str, Any]:
        mission = self.cycle.mission
        baseline = [dict(r, **self.baseline_routes.get(r["id"], {})) for r in obs["routes"]]
        after = [dict(r) for r in obs["routes"]]
        for rep in repairs:
            exp = rep.change.expected_postcondition
            for r in after:
                if r["id"] == exp.get("route_id"):
                    r["status"], r["narrow_to"] = exp["status"], exp.get("narrow_to")
        findings = (obs.get("findings") or [])
        tb = build_twin(baseline, findings, mission)
        ta = build_twin(after, findings, mission)
        eb = {a: max(tb.max_path_prob(f, a) for f in tb.footholds) for a in tb.protected}
        ea = {a: max(ta.max_path_prob(f, a) for f in ta.footholds) for a in ta.protected}
        return {"baseline": {k: round(v, 6) for k, v in eb.items()}, "after_repair": {k: round(v, 6) for k, v in ea.items()},
                "within_baseline": all(ea[a] <= eb[a] + 1e-9 for a in eb)}

    # ---- run -----------------------------------------------------------------------
    async def run(self, incident_id: str) -> IncidentReport:
        fsm = IncidentFSM(incident_id)
        rep = IncidentReport(incident_id, fsm.state)
        await self.cycle.broker.connect_and_pin_manifest()
        obs = await self._observe()
        obs["findings"] = (await self.cycle.broker.invoke("list_vuln_findings")).result.get("findings", [])
        probes = self._probes(obs)
        direct = self._direct_faults(obs)
        hidden, orphan = self._localize(probes, direct)
        faults = direct + hidden
        rep.probes = [asdict(p) for p in probes]
        guard = self.cycle.mission_guard
        for f in faults:
            if not f.affected_flows:
                rid = f.component.split(":", 1)[1]
                f.affected_flows = [fl for fl, r in self.flow_route.items() if r == rid]
            if guard is not None and f.component.startswith("route:"):
                f.tier = guard.context.get(f.component.split(":", 1)[1]).tier
        rep.faults = [asdict(f) for f in faults]
        for flow in orphan:
            rep.escalations.append({"flow": flow, "reason": "failed probe with no unexonerated component"})
        if not faults:
            fsm.fire("no_fault", "all probes healthy or inconclusive; no drift")
            return self._finish(rep, fsm)
        fsm.fire("diagnosed", f"{len(direct)} direct, {len(hidden)} localised")

        repairs: List[Repair] = []
        for f in faults:
            ch = self._repair_for(f, obs)
            if ch is None:
                rep.escalations.append({"fault": f.fault_id, "reason": "no contract tool repairs this component"})
                continue
            if guard is not None and f.component.startswith("route:"):
                bad = [v for v in guard.validate([{"route_id": ch.route_id, "xiid_action": ch.xiid_action,
                                                   "reversible": True}], self.cycle.clock(), require_window=False)
                       if v.rule_id.startswith("R-NO-AUTO") or v.rule_id.startswith("R-CCTV")]
                if bad:
                    rep.escalations.append({"fault": f.fault_id, "reason": "protected route: manual repair required",
                                            "rules": [v.rule_id for v in bad]})
                    continue
            repairs.append(Repair(f.fault_id, ch, f.tier))
        repairs.sort(key=lambda r: (r.tier if r.tier is not None else 9, r.change.change_id))
        rep.exposure = self._exposure_check(obs, repairs)
        if not repairs:
            fsm.fire("unrepairable", "no automatically repairable fault")
            return self._finish(rep, fsm)
        if not rep.exposure["within_baseline"]:
            fsm.fire("unrepairable", "repair plan would exceed approved baseline exposure")
            return self._finish(rep, fsm)
        fsm.fire("planned", f"{len(repairs)} repairs")

        auths = {}
        for r in repairs:
            try:
                auths[r.change.change_id] = self.cycle._authorize(incident_id, r.change)  # noqa: SLF001
            except Exception as exc:
                auths[r.change.change_id] = {"gate_satisfied": False, "error": str(exc)[:160]}
        if not all(a.get("gate_satisfied") for a in auths.values()):
            rep.repairs = [self._rep_dict(r, auths, "denied") for r in repairs]
            fsm.fire("denied", "approval not satisfied for every repair")
            return self._finish(rep, fsm)
        fsm.fire("authorized")

        fsm.fire("repair_started")
        applied: List[Repair] = []
        state: Dict[str, str] = {}
        for r in repairs:
            try:
                await self.cycle.broker.invoke(r.change.xiid_action, r.change.arguments,
                                               envelope=auths[r.change.change_id]["write_envelope"],
                                               idempotency_key=f"{incident_id}:{r.change.change_id}")
                applied.append(r)
                state[r.change.change_id] = "applied" if await self._postcondition(r) else "postcondition_failed"
            except Exception as exc:
                state[r.change.change_id] = f"error: {type(exc).__name__}: {str(exc)[:120]}"
            if state[r.change.change_id] != "applied":
                break
        rep.repairs = [self._rep_dict(r, auths, state.get(r.change.change_id, "not_attempted")) for r in repairs]
        if any(v != "applied" for v in state.values()) or len(state) < len(repairs):
            fsm.fire("repair_failed", "a repair did not take effect")
            # Repairs restore approved state; no inverse returns to a broken state, so escalate.
            fsm.fire("rollback_failed", "no safe inverse for restoration repairs; operator required")
            rep.escalations.append({"reason": "repair failed", "states": state})
            return self._finish(rep, fsm)
        fsm.fire("repairs_applied")

        after = await self._observe()
        after_probes = self._probes(after)
        still_failed = [p.flow_id for p in after_probes if p.verdict == "failed"]
        remaining = self._direct_faults(after)
        rep.probes_after = [asdict(p) for p in after_probes]
        if still_failed or remaining:
            fsm.fire("verification_failed", f"failed={still_failed} drift={[f.component for f in remaining]}")
            fsm.fire("rollback_failed", "restoration incomplete; operator required")
            rep.escalations.append({"reason": "verification failed", "failed_probes": still_failed,
                                    "remaining_drift": [f.component for f in remaining]})
            return self._finish(rep, fsm)
        fsm.fire("verified", "all probes healthy; baseline restored")
        return self._finish(rep, fsm)

    async def _postcondition(self, r: Repair) -> bool:
        exp = r.change.expected_postcondition
        if "route_id" in exp:
            routes = (await self.cycle.broker.invoke("list_routes")).result["routes"]
            cur = next((x for x in routes if x["id"] == exp["route_id"]), None)
            return cur is not None and cur.get("status") == exp["status"] and cur.get("narrow_to") == exp.get("narrow_to")
        stl = (await self.cycle.broker.invoke("list_stlinks")).result["stlinks"]
        cur = next((x for x in stl if x["id"] == exp["stlink_id"]), None)
        return cur is not None and cur.get("status") == "active"

    @staticmethod
    def _rep_dict(r: Repair, auths: Mapping[str, Any], state: str) -> Dict[str, Any]:
        a = auths.get(r.change.change_id, {})
        return {"fault_id": r.fault_id, "tier": r.tier, "action": r.change.xiid_action, "arguments": r.change.arguments,
                "approvals": len(a.get("votes", [])), "change_class": a.get("change_class"), "state": state}

    @staticmethod
    def _finish(rep: IncidentReport, fsm: IncidentFSM) -> IncidentReport:
        rep.state = fsm.state
        rep.history = list(fsm.history)
        return rep


def snapshot_baseline(routes: Sequence[Mapping[str, Any]], stlinks: Sequence[Mapping[str, Any]]
                      ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Approved baseline from a verified observation."""
    return ({r["id"]: {"status": r.get("status"), "narrow_to": r.get("narrow_to"),
                       "observed_sessions_30d": r.get("observed_sessions_30d", 0)} for r in routes},
            {s["id"]: {"status": s.get("status")} for s in stlinks})


__all__ = ["AutoHeal", "Fault", "IncidentReport", "Probe", "snapshot_baseline"]
