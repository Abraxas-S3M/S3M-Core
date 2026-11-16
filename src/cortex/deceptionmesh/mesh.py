"""DeceptionMesh: isolated decoys placed where an adversary will meet them first (capability 10).

Military/tactical context:
A decoy has no legitimate users, so any touch is a high-fidelity signal. Its value depends
entirely on placement: a decoy nobody passes is decoration. DeceptionMesh places a small
number of decoys where simulated campaigns on the CyberTwin are most likely to touch one
*before* reaching a protected asset, deploys them through the (PROPOSED) contract tools
with approvals, proves they are isolated and that no productive route changed, and turns
interactions into evidence for GhostShift and containment.

Placement:
- simulate adversary spread (same model as CyberWarGame) for several campaigns; record when
  each node falls and when the first protected asset falls;
- a decoy attached at node ``u`` is touched at the first hour after ``u`` falls in which the
  lure succeeds (hourly probability ``q``), drawn once per run and node so every placement
  is judged on the same adversary luck;
- objective: P(some decoy touched before the first protected asset is lost), averaged over
  campaigns and runs. It is monotone submodular (a maximum of indicators), so greedy
  placement carries the (1 - 1/e) guarantee; small k is also solved exhaustively to measure
  the actual gap.

Rules: decoys are internal only (never internet-facing), never attached to protected assets
or to a protected segment's hosts, never on a productive host (decoy hosts are separate),
and have no outbound route. Interaction telemetry is bounded to who/when/how often/how
deep: never payloads.

The decoy tools are PROPOSED contract extensions, range only: REQUIRES XIID VALIDATION.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from src.cortex.architect import ProposedChange
from src.cortex.cybertwin import CyberTwinGraph

INF = 10**9


@dataclass
class Trajectory:
    fell: Dict[str, int]  # node -> hour compromised
    first_loss: int  # hour first protected asset fell (INF if never)


def simulate_spread(twin: CyberTwinGraph, entry: Sequence[str], *, hours: int = 168, hop_hours: float = 24.0,
                    seed: int = 0) -> Trajectory:
    rng = random.Random(seed)
    fell = {n: 0 for n in entry}
    edges = sorted(twin.edges.values(), key=lambda e: e.edge_id)
    first_loss = INF
    for h in range(1, hours):
        new = []
        for e in edges:
            if e.removed or e.source not in fell or e.target in fell:
                continue
            if rng.random() < e.p / hop_hours:
                new.append(e.target)
        for n in new:
            fell.setdefault(n, h)
            if n in twin.protected:
                first_loss = min(first_loss, h)
    return Trajectory(fell, first_loss)


def candidates(twin: CyberTwinGraph, *, forbidden: Sequence[str] = ()) -> List[str]:
    return sorted(n for n in twin.nodes if not n.startswith("ext:") and n not in twin.protected
                  and n not in set(forbidden) and not n.startswith("decoy-"))


@dataclass
class PlacementModel:
    touch: List[Dict[str, int]]  # per run: candidate -> touch hour (INF if never)
    loss: List[int]

    def score(self, placement: Sequence[str]) -> float:
        if not placement:
            return 0.0
        hits = 0
        for t, loss in zip(self.touch, self.loss):
            first = min(t[c] for c in placement)
            hits += first < INF and first < loss
        return hits / len(self.loss)

    def lead_hours(self, placement: Sequence[str]) -> float:
        leads = []
        for t, loss in zip(self.touch, self.loss):
            first = min(t[c] for c in placement)
            if first < loss and loss < INF:
                leads.append(loss - first)
        return round(mean(leads), 1) if leads else 0.0


def build_model(twin: CyberTwinGraph, campaigns: Sequence[Sequence[str]], cands: Sequence[str], *, runs: int = 200,
                lure_per_hour: float = 0.15, hours: int = 168, seed: int = 0) -> PlacementModel:
    touch, loss = [], []
    for ci, entry in enumerate(campaigns):
        for r in range(runs):
            s = seed * 1_000_003 + ci * 10_007 + r
            tr = simulate_spread(twin, entry, hours=hours, seed=s)
            lr = random.Random(s * 31 + 7)
            row = {}
            for c in cands:
                if c not in tr.fell:
                    row[c] = INF
                    continue
                h = tr.fell[c]
                while h < hours and lr.random() >= lure_per_hour:
                    h += 1
                row[c] = h if h < hours else INF
            touch.append(row)
            loss.append(tr.first_loss)
    return PlacementModel(touch, loss)


def greedy(model: PlacementModel, cands: Sequence[str], k: int) -> List[str]:
    chosen: List[str] = []
    for _ in range(k):
        best = max((c for c in cands if c not in chosen),
                   key=lambda c: (model.score(chosen + [c]), model.lead_hours(chosen + [c]), c), default=None)
        if best is None or model.score(chosen + [best]) <= model.score(chosen):
            break  # no candidate adds detection: do not deploy decoys for show
        chosen.append(best)
    return chosen


def exhaustive(model: PlacementModel, cands: Sequence[str], k: int) -> Tuple[List[str], float]:
    best, best_s = [], -1.0
    for combo in itertools.combinations(cands, k):
        sc = model.score(list(combo))
        if sc > best_s:
            best, best_s = list(combo), sc
    return best, best_s


def crown_jewel_adjacent(twin: CyberTwinGraph, cands: Sequence[str], k: int) -> List[str]:
    """Common practice: decoys next to the most valuable systems (direct predecessors of protected assets)."""
    score: Dict[str, float] = {}
    for e in twin.edges.values():
        if e.target in twin.protected and e.source in cands and not e.removed:
            score[e.source] = max(score.get(e.source, 0.0), e.p)
    return [c for c, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))][:k]


def random_baseline(model: PlacementModel, cands: Sequence[str], k: int, *, trials: int = 50, seed: int = 0) -> float:
    rng = random.Random(seed)
    return mean(model.score(rng.sample(list(cands), k)) for _ in range(trials))


# ---- deployment ------------------------------------------------------------------------------

PERSONA = {"grp": ("smb", "file-share"), "seg": ("https", "admin-portal"), "server": ("https", "service-console")}


def decoy_plan(placement: Sequence[str]) -> List[Dict[str, str]]:
    out = []
    for i, node in enumerate(placement):
        kind = node.split(":", 1)[0] if ":" in node else "server"
        service, persona = PERSONA.get(kind, PERSONA["server"])
        slug = node.replace(":", "-")[:30]
        out.append({"decoy_id": f"decoy-{i + 1}-{slug}"[:46], "attach": node, "service": service, "persona": persona})
    return out


def deploy_change(d: Mapping[str, str]) -> ProposedChange:
    return ProposedChange(
        change_id=f"deception-{d['decoy_id']}", route_id="rt-decoy-" + d["decoy_id"].removeprefix("decoy-"),
        twin_action="decoy", xiid_action="deploy_decoy", arguments=dict(d), rollback_action="retire_decoy",
        rollback_arguments={"decoy_id": d["decoy_id"]}, reversible=True, risk_before=0.0, risk_after=0.0, cost=0.5,
        disrupted_sessions_30d=0, rationale=f"DeceptionMesh: isolated {d['persona']} decoy reachable from {d['attach']}",
        expected_postcondition={"decoy_id": d["decoy_id"], "status": "active"})


@dataclass
class DeployReport:
    deployed: List[str] = field(default_factory=list)
    refused: List[Dict[str, str]] = field(default_factory=list)
    productive_routes_unchanged: bool = True
    decoys_isolated: bool = True
    lure_routes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def deploy(plan: Sequence[Mapping[str, str]], *, cycle, case_id: str) -> DeployReport:
    b = cycle.broker
    await b.connect_and_pin_manifest()
    rep = DeployReport()
    before = (await b.invoke("list_routes")).result["routes"]
    for d in plan:
        ch = deploy_change(d)
        auth = cycle._authorize(case_id, ch)  # noqa: SLF001 - same approval path as every change
        if not auth.get("gate_satisfied"):
            rep.refused.append({"decoy": d["decoy_id"], "reason": "approval not satisfied"})
            continue
        try:
            await b.invoke("deploy_decoy", dict(d), envelope=auth["write_envelope"],
                           idempotency_key=f"{case_id}:{ch.change_id}")
            rep.deployed.append(d["decoy_id"])
        except Exception as exc:  # the control plane enforces placement rules too
            rep.refused.append({"decoy": d["decoy_id"], "reason": str(exc)[:160]})
    after = (await b.invoke("list_routes")).result["routes"]
    rep.productive_routes_unchanged, rep.decoys_isolated, rep.lure_routes = verify_isolation(before, after)
    return rep


async def retire(decoy_ids: Sequence[str], *, cycle, case_id: str) -> List[str]:
    """Retire decoys through the same approval path; returns the ids retired."""
    done = []
    for did in decoy_ids:
        ch = ProposedChange(
            change_id=f"deception-retire-{did}", route_id="rt-decoy-" + did.removeprefix("decoy-"), twin_action="decoy",
            xiid_action="retire_decoy", arguments={"decoy_id": did}, rollback_action=None, rollback_arguments=None,
            reversible=True, risk_before=0.0, risk_after=0.0, cost=0.1, disrupted_sessions_30d=0,
            rationale=f"DeceptionMesh: retire {did}", expected_postcondition={"decoy_id": did, "status": "retired"})
        auth = cycle._authorize(case_id, ch)  # noqa: SLF001
        if auth.get("gate_satisfied"):
            await cycle.broker.invoke("retire_decoy", {"decoy_id": did}, envelope=auth["write_envelope"],
                                      idempotency_key=f"{case_id}:{ch.change_id}")
            done.append(did)
    return done


def verify_isolation(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]
                     ) -> Tuple[bool, bool, List[str]]:
    """Productive routes identical; every new route is an inbound lure to a decoy; nothing leaves a decoy."""
    key = lambda r: (r.get("source"), r.get("target"), r.get("status"), r.get("prefix"), r.get("narrow_to"))  # noqa: E731
    prod_b = {r["id"]: key(r) for r in before if not r.get("decoy")}
    prod_a = {r["id"]: key(r) for r in after if not r.get("decoy")}
    lures = [r for r in after if r.get("decoy")]
    isolated = all(str(r["target"]).startswith("decoy-") for r in lures) and not any(
        str(r["source"]).startswith("decoy-") for r in after)
    return prod_b == prod_a, isolated, sorted(r["id"] for r in lures)


async def collect(cycle, *, decoy_attach: Mapping[str, str]) -> Dict[str, Any]:
    """Interactions -> compromise evidence (the attach point and the touching source are implicated)."""
    res = (await cycle.broker.invoke("decoy_interactions", {})).result["interactions"]
    hosts = sorted({i["source"] for i in res} | {decoy_attach[i["decoy_id"]] for i in res if i["decoy_id"] in decoy_attach})
    return {"interactions": res, "evidence": {"hosts": hosts, "kind": "decoy_touch",
                                              "max_depth": max((i["max_depth"] for i in res), default=0)}}


def placement_value(twin: CyberTwinGraph, wargame, placement: Sequence[str], *, campaign, lure_per_hour: float = 0.15,
                    runs: int = 150, seed: int = 1, playbook: str = "quarantine_detected") -> Dict[str, float]:
    """Assets lost under a playbook with and without the decoys (CyberWarGame, same draws)."""
    without = wargame.compare(campaign, runs=runs, seed=seed)[playbook]
    with_ = wargame.compare(campaign, runs=runs, seed=seed, decoys={n: lure_per_hour for n in placement})[playbook]
    return {"assets_lost_without": round(without.mean_assets_lost, 3), "assets_lost_with": round(with_.mean_assets_lost, 3),
            "losses_without": without.losses, "losses_with": with_.losses}


__all__ = ["DeployReport", "PlacementModel", "Trajectory", "build_model", "candidates", "collect",
           "crown_jewel_adjacent", "decoy_plan", "deploy", "exhaustive", "greedy", "placement_value",
           "random_baseline", "retire", "simulate_spread", "verify_isolation"]

