"""CyberWarGame: rehearse incident campaigns on the twin and compare containment (capability 09).

Military/tactical context:
Before an incident, commanders need to know which containment playbook to trust: isolate
the compromised segment, cut its egress, ring-fence the crown jewels, or apply an optimised
cut. Each costs service availability. This module runs many synthetic campaigns on the
CyberTwin and compares playbooks under the same attacker luck, so differences are due to
the playbook, not the dice.

Simulation (one campaign, hourly steps):
- the attacker holds a set of nodes, starting at the campaign's entry. Each hour it tries
  every live edge out of that set; an edge with twin probability ``p`` succeeds with
  hourly probability ``p / hop_hours``. Identity edges are traversable; Cortex cannot cut
  them (they are not routes);
- the defender detects each compromised node with an hourly probability set by the
  detection profile. ``response_hours`` after the first detection, the playbook runs once,
  using only what has been *detected*; undetected nodes keep spreading;
- outcome: protected assets lost (and when), required-flow hours lost (weighted by mission
  tier), and whether the attacker was contained.

Comparison: common random numbers (identical attacker and detection draws for every
playbook), paired bootstrap confidence intervals on differences, and a Pareto front over
(mission loss, availability loss). A playbook is called better only when the interval
excludes zero.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from src.cortex.breachpath.optimizer import PlanConstraints, optimize
from src.cortex.cybertwin import NARROW_FACTOR, CyberTwinGraph

Playbook = Callable[[CyberTwinGraph, Set[str]], "Containment"]


@dataclass
class Containment:
    name: str
    removed_edges: Set[str] = field(default_factory=set)  # edge ids
    scaled_edges: Dict[str, float] = field(default_factory=dict)  # edge id -> factor (narrowing)
    quarantined: Set[str] = field(default_factory=set)
    actions: List[str] = field(default_factory=list)


@dataclass
class Campaign:
    campaign_id: str
    entry: List[str]
    hours: int = 168  # one week
    hop_hours: float = 24.0  # an edge with p = 1 takes a day on average
    response_hours: int = 2


@dataclass
class RunOutcome:
    assets_lost: Dict[str, int]  # asset -> hour compromised
    flow_hours_lost: float  # tier-weighted
    detected_at: Optional[int]
    contained: bool
    actions: List[str]


@dataclass
class PlaybookResult:
    playbook: str
    p_any_asset_lost: float
    mean_assets_lost: float
    mean_flow_hours_lost: float
    p_contained: float
    mean_actions: float
    losses: List[float] = field(default_factory=list, repr=False)
    flow_losses: List[float] = field(default_factory=list, repr=False)
    detected_at: List[Optional[int]] = field(default_factory=list, repr=False)


DEFAULT_DETECTION = {"server": 0.02, "protected": 0.05, "grp": 0.005, "ext": 0.0}  # per node-hour
TIER_WEIGHT = {1: 10.0, 2: 3.0, 3: 1.0, None: 0.5}


class WarGame:
    def __init__(self, twin: CyberTwinGraph, *, flow_tiers: Mapping[str, Optional[int]],
                 detection: Optional[Mapping[str, float]] = None) -> None:
        self.twin = twin
        self.flow_tiers = dict(flow_tiers)
        self.detection = dict(DEFAULT_DETECTION, **(detection or {}))
        self.edge_ids = sorted(twin.edges)
        self.node_ids = sorted(twin.nodes)
        self.flow_edge = {fid: twin.route_edge.get(rid) for fid, rid in twin.flow_routes.items()}

    # ---- playbooks ------------------------------------------------------------------
    def _detect_p(self, node: str) -> float:
        if node in self.twin.protected:
            return self.detection["protected"]
        kind = node.split(":", 1)[0] if ":" in node else "server"
        return self.detection.get(kind, self.detection["server"])

    def playbooks(self) -> Dict[str, Playbook]:
        g = self.twin

        def none(_: CyberTwinGraph, detected: Set[str]) -> Containment:
            return Containment("none")

        def quarantine(_: CyberTwinGraph, detected: Set[str]) -> Containment:
            q = {n for n in detected if not n.startswith("ext:")}
            return Containment("quarantine_detected", quarantined=q, actions=[f"host.quarantine {n}" for n in sorted(q)])

        def cut_egress(_: CyberTwinGraph, detected: Set[str]) -> Containment:
            rm = {e.edge_id for e in g.edges.values() if e.source in detected and e.kind == "route" and not e.removed}
            return Containment("cut_egress", removed_edges=rm, actions=[f"route.expire {g.route_meta[e].route_id}"
                                                                        for e in sorted(rm)])

        def ring_fence(_: CyberTwinGraph, detected: Set[str]) -> Containment:
            keep = {self.flow_edge[f] for f, t in self.flow_tiers.items() if t == 1}
            rm = {e.edge_id for e in g.edges.values() if e.target in g.protected and e.kind == "route"
                  and not e.removed and e.edge_id not in keep}
            return Containment("ring_fence_assets", removed_edges=rm,
                               actions=[f"route.expire {g.route_meta[e].route_id}" for e in sorted(rm)])

        def adaptive(_: CyberTwinGraph, detected: Set[str]) -> Containment:
            sim = g.clone()
            sim.footholds = set(g.footholds) | {n for n in detected if n in g.nodes}
            sim._path_cache.clear()  # noqa: SLF001
            tier1 = {g.flow_routes[f] for f, t in self.flow_tiers.items() if t == 1}
            forbidden = {rid: {"expire", "narrow"} for rid in tier1}
            plan = optimize(sim, threshold=0.05, time_limit=5.0,
                            constraints=PlanConstraints(forbidden=forbidden, expire_policy="any", expire_reversible=True))
            c = Containment("breachpath_adaptive")
            for a in plan.actions:
                eid = g.route_edge[a.route_id]
                if a.action == "expire":
                    c.removed_edges.add(eid)
                else:
                    c.scaled_edges[eid] = NARROW_FACTOR
                c.actions.append(f"route.{a.action} {a.route_id}")
            return c

        return {"none": none, "quarantine_detected": quarantine, "cut_egress": cut_egress,
                "ring_fence_assets": ring_fence, "breachpath_adaptive": adaptive}

    # ---- simulation ------------------------------------------------------------------
    def _draws(self, campaign: Campaign, seed: int) -> Tuple[List[List[float]], ...]:
        rng = random.Random(seed)
        edge = [[rng.random() for _ in self.edge_ids] for _ in range(campaign.hours)]
        det = [[rng.random() for _ in self.node_ids] for _ in range(campaign.hours)]
        # Decoy lure draws per node: independent of placement, so placements share attacker luck.
        rng2 = random.Random(seed * 7919 + 1)
        lure = [[rng2.random() for _ in self.node_ids] for _ in range(campaign.hours)]
        return edge, det, lure

    def run(self, campaign: Campaign, playbook: Playbook, draws,
            decoys: Optional[Mapping[str, float]] = None, boost: Optional[Tuple[int, float]] = None) -> RunOutcome:
        """``decoys``: attach node -> hourly probability an adversary there touches the decoy
        (a touch is a high-fidelity detection of that node; DeceptionMesh)."""
        g = self.twin
        edge_u, det_u = draws[0], draws[1]
        lure_u = draws[2] if len(draws) > 2 else None
        decoys = dict(decoys or {})
        comp: Set[str] = set(campaign.entry)
        detected: Set[str] = set()
        first_det: Optional[int] = None
        cont: Optional[Containment] = None
        lost: Dict[str, int] = {}
        flow_loss = 0.0
        e_idx = {e: i for i, e in enumerate(self.edge_ids)}
        n_idx = {n: i for i, n in enumerate(self.node_ids)}
        for hour in range(campaign.hours):
            if cont is None and first_det is not None and hour >= first_det + campaign.response_hours:
                cont = playbook(g, set(detected))
            new = set()
            for eid in self.edge_ids:
                e = g.edges[eid]
                if e.source not in comp or e.target in comp or e.removed:
                    continue
                p = e.p
                if cont is not None:
                    if eid in cont.removed_edges or e.source in cont.quarantined or e.target in cont.quarantined:
                        continue
                    p *= cont.scaled_edges.get(eid, 1.0)
                if edge_u[hour][e_idx[eid]] < p / campaign.hop_hours:
                    new.add(e.target)
            comp |= new
            for a in new & g.protected:
                lost.setdefault(a, hour)
            for n in comp - detected:
                touched = (n in decoys and lure_u is not None and lure_u[hour][n_idx[n]] < decoys[n])
                factor = boost[1] if boost is not None and hour >= boost[0] else 1.0  # e.g. a partner's indicator
                if touched or det_u[hour][n_idx[n]] < min(1.0, self._detect_p(n) * factor):
                    detected.add(n)
                    first_det = hour if first_det is None else first_det
            if cont is not None:
                for fid, eid in self.flow_edge.items():
                    e = g.edges.get(eid) if eid else None
                    if e is None:
                        continue
                    down = eid in cont.removed_edges or e.source in cont.quarantined or e.target in cont.quarantined
                    if down:
                        flow_loss += TIER_WEIGHT.get(self.flow_tiers.get(fid), 0.5)
        frontier = self._can_progress(comp, cont)
        return RunOutcome(lost, flow_loss, first_det, bool(cont and cont.actions) and not frontier,
                          cont.actions if cont else [])

    def _can_progress(self, comp: Set[str], cont: Optional[Containment]) -> bool:
        for e in self.twin.edges.values():
            if e.source in comp and e.target not in comp and not e.removed and e.p > 0:
                if cont and (e.edge_id in cont.removed_edges or e.source in cont.quarantined
                             or e.target in cont.quarantined):
                    continue
                return True
        return False

    def compare(self, campaign: Campaign, *, runs: int = 300, seed: int = 0,
                playbooks: Optional[Mapping[str, Playbook]] = None,
                decoys: Optional[Mapping[str, float]] = None,
                boosts: Optional[Sequence[Optional[Tuple[int, float]]]] = None) -> Dict[str, PlaybookResult]:
        """``boosts[i]``: (hour, factor) from which run i's detection is multiplied (CyberSwarm)."""
        pbs = playbooks or self.playbooks()
        draws = [self._draws(campaign, seed * 100_003 + i) for i in range(runs)]
        out = {}
        for name, pb in pbs.items():
            outs = [self.run(campaign, pb, d, decoys, boosts[i] if boosts else None) for i, d in enumerate(draws)]
            out[name] = PlaybookResult(
                name, sum(bool(o.assets_lost) for o in outs) / runs, sum(len(o.assets_lost) for o in outs) / runs,
                sum(o.flow_hours_lost for o in outs) / runs, sum(o.contained for o in outs) / runs,
                sum(len(o.actions) for o in outs) / runs,
                losses=[float(len(o.assets_lost)) for o in outs], flow_losses=[o.flow_hours_lost for o in outs],
                detected_at=[o.detected_at for o in outs])
        return out


def paired_ci(a: Sequence[float], b: Sequence[float], *, iters: int = 2000, seed: int = 1,
              level: float = 0.95) -> Tuple[float, float, float]:
    """Mean of (a - b) with a percentile bootstrap interval (paired by run)."""
    d = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    n = len(d)
    means = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    lo = means[int((1 - level) / 2 * iters)]
    hi = means[min(iters - 1, int((1 + level) / 2 * iters))]
    return sum(d) / n, lo, hi


def pareto(results: Mapping[str, PlaybookResult]) -> List[str]:
    """Playbooks not dominated on (mean assets lost, mean flow-hours lost)."""
    pts = {k: (v.mean_assets_lost, v.mean_flow_hours_lost) for k, v in results.items()}
    return sorted(k for k, (x, y) in pts.items()
                  if not any((x2 <= x and y2 <= y) and (x2 < x or y2 < y) for k2, (x2, y2) in pts.items() if k2 != k))


def recommend(results: Mapping[str, PlaybookResult], *, max_flow_hours: float) -> Optional[str]:
    """Lowest mission loss among playbooks within the availability budget (ties: fewer flow-hours)."""
    ok = [r for r in results.values() if r.mean_flow_hours_lost <= max_flow_hours]
    if not ok:
        return None
    return min(ok, key=lambda r: (round(r.mean_assets_lost, 6), r.mean_flow_hours_lost, r.playbook)).playbook


def flow_tiers_from_policy(policy) -> Dict[str, Optional[int]]:
    tiers: Dict[str, Optional[int]] = {}
    for m in policy.missions:
        for f in m.flows:
            tiers[f] = min(m.tier, tiers.get(f) or m.tier)
    return tiers


__all__ = ["Campaign", "Containment", "PlaybookResult", "RunOutcome", "WarGame", "flow_tiers_from_policy",
           "paired_ci", "pareto", "recommend"]

