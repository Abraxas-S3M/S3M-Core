"""Predictive Exposure Radar: which weakness will matter to the mission, and when (capability 08).

Military/tactical context:
Patch queues sorted by CVSS treat a critical flaw on an isolated print server like one on
the path to the financial database. The radar correlates vulnerability intelligence (CVSS,
EPSS, KEV) with what an attacker can actually reach on the CyberTwin, and looks forward:
EPSS is a 30-day probability of exploitation activity, so a reachable flaw with a rising
EPSS is flagged before it is weaponised.

Three pieces:

1. **Path importance (counterfactual).** For each finding, the drop in mission exposure
   ``M = sum_a w_a * max_f P(path f -> a)`` if that finding alone were fixed, computed on
   the twin with findings projected to the horizon (EPSS_T = 1 - (1 - EPSS)^(T/30)).
   Redundant paths make single-finding importance zero; the ordering uses pair lookahead
   when that happens.
2. **Patch ordering.** Sequential counterfactual greedy: repeatedly fix the finding whose
   removal most reduces projected mission exposure (per unit patch cost), re-scoring after
   each pick because importance changes once a parallel path is closed.
3. **Intelligence ingest.** EPSS updates, KEV additions, new findings and route changes
   re-score incrementally; an alert fires only when the mission impact changes enough
   (enters the top N, or importance rises by more than a threshold).

Evaluation (``simulate``) is a Monte Carlo over SYNTHETIC futures in which each finding is
weaponised at an exponential time implied by its EPSS. It measures mission exposure-days
under a weekly patch capacity for each ordering policy. It assumes EPSS is calibrated; that
assumption is the main limit on any claim made from it.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.cortex.cybertwin import build_twin

Finding = Mapping[str, Any]


def project(f: Finding, horizon_days: float) -> Dict[str, Any]:
    """EPSS over ``horizon_days`` (EPSS is a 30-day probability; constant hazard assumed)."""
    epss = min(0.999999, max(0.0, float(f.get("epss", 0.0))))
    return dict(f, epss=1.0 - (1.0 - epss) ** (horizon_days / 30.0))


class ExposureModel:
    """Mission exposure on the twin with a cache keyed by the finding set."""

    def __init__(self, routes: Sequence[Mapping[str, Any]], mission: Mapping[str, Any],
                 weights: Optional[Mapping[str, float]] = None) -> None:
        self.routes = [dict(r) for r in routes]
        self.mission = mission
        self.weights = dict(weights or {a: 1.0 for a in mission.get("protected_assets", {})})
        self._cache: Dict[Tuple, Tuple[float, Dict[str, float]]] = {}

    @staticmethod
    def _key(findings: Iterable[Finding]) -> Tuple:
        return tuple(sorted((str(f["id"]), str(f.get("host")), str(f.get("service")), round(float(f.get("cvss", 0)), 3),
                             round(float(f.get("epss", 0)), 6), bool(f.get("kev"))) for f in findings))

    def exposure(self, findings: Sequence[Finding]) -> Tuple[float, Dict[str, float]]:
        key = self._key(findings)
        hit = self._cache.get(key)
        if hit is None:
            twin = build_twin(self.routes, findings, self.mission)
            per = {a: max((twin.max_path_prob(ft, a) for ft in twin.footholds), default=0.0) for a in twin.protected}
            hit = (sum(self.weights.get(a, 0.0) * p for a, p in per.items()), per)
            if len(self._cache) > 200_000:
                self._cache.clear()
            self._cache[key] = hit
        return hit


@dataclass
class RadarEntry:
    finding_id: str
    host: str
    cvss: float
    epss: float
    kev: bool
    epss_horizon: float
    importance: float  # drop in projected mission exposure if this finding alone is fixed
    reachable: bool  # some foothold has a positive-probability path to the host
    rank: int = 0
    rank_cvss: int = 0


def importance(model: ExposureModel, findings: Sequence[Finding]) -> Dict[str, float]:
    base, _ = model.exposure(findings)
    out = {}
    for i, f in enumerate(findings):
        without = list(findings[:i]) + list(findings[i + 1:])
        out[str(f["id"])] = max(0.0, base - model.exposure(without)[0])
    return out


def radar_order(model: ExposureModel, findings: Sequence[Finding], *, horizon_days: float = 30.0,
                cost: Optional[Mapping[str, float]] = None) -> List[str]:
    """Sequential counterfactual greedy with pair lookahead on all-zero rounds."""
    remaining = [project(f, horizon_days) for f in findings]
    cost = cost or {}
    order: List[str] = []
    while remaining:
        imp = importance(model, remaining)
        score = {fid: v / max(1e-9, float(cost.get(fid, 1.0))) for fid, v in imp.items()}
        best = max(remaining, key=lambda f: (score[str(f["id"])], float(f["epss"]), float(f.get("cvss", 0)), str(f["id"])))
        if score[str(best["id"])] <= 1e-12 and len(remaining) > 1:
            base = model.exposure(remaining)[0]
            pair_best, pair_gain = None, 0.0
            for a, b in itertools.combinations(range(len(remaining)), 2):
                rest = [f for k, f in enumerate(remaining) if k not in (a, b)]
                gain = base - model.exposure(rest)[0]
                if gain > pair_gain + 1e-12:
                    pair_best, pair_gain = (remaining[a], remaining[b]), gain
            if pair_best is not None:
                best = max(pair_best, key=lambda f: (float(f["epss"]), float(f.get("cvss", 0)), str(f["id"])))
        order.append(str(best["id"]))
        remaining = [f for f in remaining if f["id"] != best["id"]]
    return order


def baseline_orders(findings: Sequence[Finding]) -> Dict[str, List[str]]:
    def by(key: Callable[[Finding], Tuple]) -> List[str]:
        return [str(f["id"]) for f in sorted(findings, key=key)]
    return {
        "cvss": by(lambda f: (-float(f.get("cvss", 0)), -float(f.get("epss", 0)), str(f["id"]))),
        "epss": by(lambda f: (-float(f.get("epss", 0)), -float(f.get("cvss", 0)), str(f["id"]))),
        "kev_then_cvss": by(lambda f: (not f.get("kev"), -float(f.get("cvss", 0)), str(f["id"]))),
    }


def exact_best_set(model: ExposureModel, findings: Sequence[Finding], k: int, *,
                   horizon_days: float = 30.0) -> Tuple[List[str], float]:
    """Exhaustive best k findings to fix first (validation of the greedy; C(n, k) twins)."""
    proj = [project(f, horizon_days) for f in findings]
    best, best_m = [], math.inf
    for combo in itertools.combinations(range(len(proj)), k):
        m = model.exposure([f for i, f in enumerate(proj) if i not in combo])[0]
        if m < best_m - 1e-12:
            best, best_m = [str(proj[i]["id"]) for i in combo], m
    return best, best_m


class ExposureRadar:
    """Stateful radar: ranked view plus alerts on intelligence or topology changes."""

    def __init__(self, routes: Sequence[Mapping[str, Any]], findings: Sequence[Finding], mission: Mapping[str, Any], *,
                 horizon_days: float = 30.0, top_n: int = 5, alert_delta: float = 0.05) -> None:
        self.routes = [dict(r) for r in routes]
        self.findings = {str(f["id"]): dict(f) for f in findings}
        self.mission = mission
        self.horizon_days = horizon_days
        self.top_n = top_n
        self.alert_delta = alert_delta
        self.view = self._score()

    def _score(self) -> Dict[str, RadarEntry]:
        model = ExposureModel(self.routes, self.mission)
        fs = list(self.findings.values())
        proj = [project(f, self.horizon_days) for f in fs]
        imp = importance(model, proj)
        twin = build_twin(self.routes, fs, self.mission)
        entries = {}
        for f, p in zip(fs, proj):
            host = str(f.get("host") or f.get("component"))
            reach = host in twin.nodes and any(twin.max_path_prob(ft, host) > 0 for ft in twin.footholds if ft != host)
            entries[str(f["id"])] = RadarEntry(str(f["id"]), host, float(f.get("cvss", 0)), float(f.get("epss", 0)),
                                               bool(f.get("kev")), round(float(p["epss"]), 4),
                                               round(imp[str(f["id"])], 6), bool(reach or host in twin.footholds))
        for i, e in enumerate(sorted(entries.values(), key=lambda e: (-e.importance, -e.epss_horizon, e.finding_id)), 1):
            e.rank = i
        for i, fid in enumerate(baseline_orders(fs)["cvss"], 1):
            entries[fid].rank_cvss = i
        return entries

    def ranked(self) -> List[RadarEntry]:
        return sorted(self.view.values(), key=lambda e: e.rank)

    def ingest(self, event: Mapping[str, Any]) -> List[Dict[str, Any]]:
        kind = event["type"]
        if kind == "epss_update":
            self.findings[event["finding_id"]]["epss"] = float(event["epss"])
        elif kind == "kev_added":
            self.findings[event["finding_id"]]["kev"] = True
        elif kind == "new_finding":
            self.findings[str(event["finding"]["id"])] = dict(event["finding"])
        elif kind == "finding_fixed":
            self.findings.pop(event["finding_id"], None)
        elif kind == "route_change":
            for r in self.routes:
                if r["id"] == event["route_id"]:
                    r.update({k: v for k, v in event.items() if k in ("status", "narrow_to")})
        else:
            raise ValueError(f"unknown radar event {kind}")
        before = self.view
        self.view = self._score()
        alerts = []
        for fid, e in self.view.items():
            old = before.get(fid)
            rose = e.importance - (old.importance if old else 0.0)
            entered = e.rank <= self.top_n and (old is None or old.rank > self.top_n)
            if e.importance > 0 and (rose >= self.alert_delta or entered):
                alerts.append({"finding_id": fid, "host": e.host, "trigger": kind,
                               "importance_before": round(old.importance, 6) if old else None,
                               "importance_after": e.importance, "rank_before": old.rank if old else None,
                               "rank_after": e.rank,
                               "reason": "entered top %d" % self.top_n if entered else "mission impact rose"})
        return sorted(alerts, key=lambda a: a["rank_after"])


# ---- evaluation over synthetic futures ------------------------------------------------------

@dataclass
class PolicyResult:
    policy: str
    mean_exposure_days: float
    p95_exposure_days: float
    exposure_at_risk: float  # P(mission exposure exceeds tau at any weekly check)
    samples: List[float] = field(default_factory=list, repr=False)


def _truth(f: Finding, weaponised: bool) -> Dict[str, Any]:
    """Ground-truth exploitability: weaponised flaws behave as KEV with EPSS 1; others need skill."""
    return dict(f, epss=1.0 if weaponised else 0.0, kev=bool(weaponised))


def simulate(model: ExposureModel, findings: Sequence[Finding], orders: Mapping[str, Sequence[str]], *,
             horizon_days: int = 91, step_days: int = 7, patches_per_step: int = 2, samples: int = 200,
             tau: float = 1.0, seed: int = 0) -> Dict[str, PolicyResult]:
    rng = random.Random(seed)
    fs = {str(f["id"]): f for f in findings}
    futures = []
    for _ in range(samples):
        t = {}
        for fid, f in fs.items():
            if f.get("kev"):
                t[fid] = 0.0
            else:
                lam = -math.log(max(1e-9, 1.0 - min(0.999999, float(f.get("epss", 0.0))))) / 30.0
                t[fid] = rng.expovariate(lam) if lam > 0 else math.inf
        futures.append(t)
    out = {}
    steps = list(range(0, horizon_days, step_days))
    for name, order in orders.items():
        totals, breaches = [], 0
        for t in futures:
            total, breached = 0.0, False
            for w, day in enumerate(steps):
                patched = set(order[: patches_per_step * w])
                active = [_truth(fs[fid], t[fid] <= day) for fid in fs if fid not in patched]
                m = model.exposure(active)[0]
                total += m * step_days
                breached = breached or (w > 0 and m > tau)  # week 0: no policy has acted yet
            totals.append(total)
            breaches += breached
        totals.sort()
        out[name] = PolicyResult(name, round(sum(totals) / len(totals), 4),
                                 round(totals[min(len(totals) - 1, int(0.95 * len(totals)))], 4),
                                 round(breaches / len(futures), 4), totals)
    return out


def synthetic_findings(routes: Sequence[Mapping[str, Any]], n: int, seed: int) -> List[Dict[str, Any]]:
    """Random finding sets on real route targets/services (for robustness, not realism)."""
    rng = random.Random(seed)
    targets = sorted({(str(r["target"]), str(r.get("service", ""))) for r in routes})
    out = []
    for i in range(n):
        host, service = rng.choice(targets)
        epss = min(0.97, rng.betavariate(0.6, 2.2))
        out.append({"id": f"SYN-R{seed}-{i:03d}", "host": host, "component": host, "service": service,
                    "cvss": round(rng.uniform(4.0, 10.0), 1), "epss": round(epss, 3),
                    "kev": rng.random() < 0.05 + 0.5 * epss, "severity": "synthetic", "summary": "synthetic"})
    return out


__all__ = ["ExposureModel", "ExposureRadar", "PolicyResult", "RadarEntry", "baseline_orders", "exact_best_set",
           "importance",
           "project", "radar_order", "simulate", "synthetic_findings"]
