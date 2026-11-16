"""CyberTwin calibration: edge beliefs learned from evidence, decaying with age.

Military/tactical context:
A single exploit probability per route invites false precision. Here every route carries a
Beta belief about P(traverse | attempted):

* prior     - the twin's finding-based heuristic, worth ``PRIOR_STRENGTH`` pseudo-attempts;
* evidence  - reviewed exercise / red-team / incident outcomes (attempts, successes);
* pooling   - routes with little evidence borrow strength from their service class
              (hierarchical Beta-Binomial, method-of-moments empirical Bayes);
* decay     - each outcome's weight halves every ``HALF_LIFE_DAYS``, so stale evidence
              widens uncertainty back toward the prior instead of freezing a confident value.

Telemetry (denied attempts, anomaly flags) measures adversary *pressure* - how often an
edge is tried - not success. It is tracked separately as a decayed Gamma-Poisson rate and
reported alongside, never folded into the success probability.

Outputs: a calibrated twin (posterior mean or a conservative quantile per edge) and Monte
Carlo exposure intervals per protected asset (p05 / p50 / p95).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from src.cortex.cybertwin import CyberTwinGraph

PRIOR_STRENGTH = 8.0
HALF_LIFE_DAYS = 90.0
PRESSURE_HALF_LIFE_HOURS = 24.0


def _age_weight(observed_at: datetime, now: datetime, half_life_days: float) -> float:
    age_days = max(0.0, (now - observed_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / half_life_days)


@dataclass
class Outcome:
    route_id: str
    attempts: int
    successes: int
    observed_at: datetime
    source: str  # exercise | red_team | incident (reviewed)


@dataclass
class EdgeBelief:
    route_id: str
    service: str
    prior_mean: float
    alpha: float
    beta: float
    effective_attempts: float
    pressure_per_hour: float = 0.0
    sources: List[str] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def interval(self, rng: np.random.Generator, q: Tuple[float, float] = (0.05, 0.95), n: int = 4000) -> Tuple[float, float]:
        s = rng.beta(self.alpha, self.beta, size=n)
        return float(np.quantile(s, q[0])), float(np.quantile(s, q[1]))


class CalibrationStore:
    def __init__(self, twin: CyberTwinGraph, *, prior_strength: float = PRIOR_STRENGTH,
                 half_life_days: float = HALF_LIFE_DAYS) -> None:
        self.twin = twin
        self.prior_strength = prior_strength
        self.half_life_days = half_life_days
        self.outcomes: List[Outcome] = []
        self.pressure_events: List[Tuple[str, int, datetime]] = []

    # ---- evidence ------------------------------------------------------------------
    def add_outcomes(self, outcomes: Iterable[Outcome]) -> None:
        for o in outcomes:
            if o.route_id not in self.twin.route_edge:
                raise KeyError(f"unknown route {o.route_id}")
            if not 0 <= o.successes <= o.attempts:
                raise ValueError(f"invalid outcome for {o.route_id}: {o.successes}/{o.attempts}")
            self.outcomes.append(o)

    def add_telemetry(self, events: Iterable[Mapping[str, Any]]) -> None:
        for ev in events:
            a = ev.get("attributes", {})
            if ev.get("type") == "flow.summary" and int(a.get("s3m.denied_attempts", 0)) > 0:
                when = datetime.fromisoformat(str(ev["time"]).replace("Z", "+00:00"))
                self.pressure_events.append((str(a["s3m.route.id"]), int(a["s3m.denied_attempts"]), when))

    # ---- inference -----------------------------------------------------------------
    def _decayed_counts(self, now: datetime) -> Dict[str, Tuple[float, float, List[str]]]:
        out: Dict[str, Tuple[float, float, List[str]]] = {}
        for o in self.outcomes:
            w = _age_weight(o.observed_at, now, self.half_life_days)
            n, s, src = out.get(o.route_id, (0.0, 0.0, []))
            out[o.route_id] = (n + w * o.attempts, s + w * o.successes, src + [o.source])
        return out

    def fit_prior_strength(self, counts: Mapping[str, Tuple[float, float, List[str]]]) -> Optional[float]:
        """Empirical-Bayes strength of the heuristic prior.

        Under a Beta(p0 k, (1 - p0) k) prior, an observed rate r = s/n around the heuristic
        p0 has E[(r - p0)^2 / (p0 (1 - p0))] = 1/n + (n - 1) / (n (k + 1)). Matching the
        observed sum over evidenced routes gives k: how much the heuristic deserves to be
        believed, measured rather than assumed. Needs >= 8 routes with >= 5 attempts.
        """
        z_sum = noise = signal = 0.0
        used = 0
        for rid, (n, s, _) in counts.items():
            if n < 5:
                continue
            p0 = min(0.98, max(0.005, self.twin.edges[self.twin.route_edge[rid]].p))
            z_sum += (s / n - p0) ** 2 / (p0 * (1 - p0))
            noise += 1.0 / n
            signal += (n - 1.0) / n
            used += 1
        if used < 8:
            return None
        excess = z_sum - noise
        if excess <= 0:
            return 50.0
        return float(min(50.0, max(1.0, signal / excess - 1.0)))

    def _class_priors(self, counts: Mapping[str, Tuple[float, float, List[str]]]) -> Dict[str, Tuple[float, float]]:
        """Service-class prior (mean, strength) by method of moments over routes with evidence.

        A class needs >= 3 routes with >= 5 effective attempts; otherwise routes keep their
        heuristic prior. The class mean is blended 50/50 with the heuristic per route.
        """
        by_class: Dict[str, List[float]] = {}
        for rid, (n, s, _) in counts.items():
            if n >= 5:
                meta = self.twin.route_meta[self.twin.route_edge[rid]]
                by_class.setdefault(meta.service, []).append(s / n)
        priors = {}
        for svc, rates in by_class.items():
            if len(rates) < 3:
                continue
            m, v = float(np.mean(rates)), float(np.var(rates, ddof=1))
            if v <= 0 or v >= m * (1 - m):
                strength = self.prior_strength
            else:
                strength = min(50.0, max(2.0, m * (1 - m) / v - 1))
            priors[svc] = (m, strength)
        return priors

    def beliefs(self, now: Optional[datetime] = None) -> Dict[str, EdgeBelief]:
        now = now or datetime.now(timezone.utc)
        counts = self._decayed_counts(now)
        fitted = self.fit_prior_strength(counts)
        base_strength = fitted if fitted is not None else self.prior_strength
        self.last_prior_strength = base_strength
        class_priors = self._class_priors(counts)
        pressure: Dict[str, float] = {}
        for rid, n, when in self.pressure_events:
            pressure[rid] = pressure.get(rid, 0.0) + n * 0.5 ** (max(0.0, (now - when).total_seconds()) / 3600 / PRESSURE_HALF_LIFE_HOURS)
        out = {}
        for eid, meta in self.twin.route_meta.items():
            p0 = min(0.98, max(0.005, self.twin.edges[eid].p))
            k = base_strength
            if meta.service in class_priors:
                cm, ck = class_priors[meta.service]
                p0, k = 0.5 * p0 + 0.5 * cm, 0.5 * k + 0.5 * ck
            n, s, src = counts.get(meta.route_id, (0.0, 0.0, []))
            out[meta.route_id] = EdgeBelief(
                route_id=meta.route_id, service=meta.service, prior_mean=round(p0, 6),
                alpha=p0 * k + s, beta=(1 - p0) * k + (n - s), effective_attempts=round(n, 3),
                pressure_per_hour=round(pressure.get(meta.route_id, 0.0) / PRESSURE_HALF_LIFE_HOURS, 4),
                sources=sorted(set(src)),
            )
        return out

    # ---- products ------------------------------------------------------------------
    def calibrated_twin(self, now: Optional[datetime] = None, *, quantile: Optional[float] = None,
                        seed: int = 0) -> CyberTwinGraph:
        """Twin with route probabilities replaced by posterior mean (or a conservative quantile)."""
        rng = np.random.default_rng(seed)
        tw = self.twin.clone()
        for rid, b in self.beliefs(now).items():
            eid = tw.route_edge[rid]
            p = b.mean if quantile is None else float(np.quantile(rng.beta(b.alpha, b.beta, 4000), quantile))
            factor = tw.edges[eid].p / max(self.twin.edges[eid].p, 1e-12)  # keep sealed/narrowed scaling
            tw.edges[eid].p = min(0.99, p * factor)
        tw._path_cache.clear()  # noqa: SLF001
        return tw

    def apply_to(self, twin: CyberTwinGraph, now: Optional[datetime] = None, *,
                 quantile: Optional[float] = None, seed: int = 0) -> CyberTwinGraph:
        """Calibrate *another* twin of the same environment (e.g. one rebuilt from a fresh
        observation). Each route keeps its own state relative to the store's baseline -
        a route narrowed since then stays scaled by the same factor."""
        rng = np.random.default_rng(seed)
        out = twin.clone()
        for rid, b in self.beliefs(now).items():
            if rid not in out.route_edge:
                continue
            eid = out.route_edge[rid]
            base = self.twin.edges[self.twin.route_edge[rid]].p
            factor = out.edges[eid].p / max(base, 1e-12)
            p = b.mean if quantile is None else float(np.quantile(rng.beta(b.alpha, b.beta, 4000), quantile))
            out.edges[eid].p = min(0.99, p * factor)
        out._path_cache.clear()  # noqa: SLF001
        return out

    def exposure_intervals(self, now: Optional[datetime] = None, *, samples: int = 300,
                           seed: int = 0) -> Dict[str, Dict[str, float]]:
        """Monte Carlo over beliefs: per-asset exposure p05 / p50 / p95 and the mean."""
        rng = np.random.default_rng(seed)
        beliefs = self.beliefs(now)
        draws: Dict[str, List[float]] = {a: [] for a in self.twin.protected}
        tw = self.twin.clone()
        base = {rid: self.twin.edges[self.twin.route_edge[rid]].p for rid in beliefs}  # incl. sealed/narrowed
        for _ in range(samples):
            for rid, b in beliefs.items():
                eid = tw.route_edge[rid]
                factor = base[rid] / max(self.twin.edges[eid].p, 1e-12)
                tw.edges[eid].p = min(0.99, float(rng.beta(b.alpha, b.beta)) * factor)
            tw._path_cache.clear()  # noqa: SLF001
            for a in tw.protected:
                draws[a].append(max((tw.max_path_prob(f, a) for f in tw.footholds), default=0.0))
        return {a: {"p05": round(float(np.quantile(v, 0.05)), 6), "p50": round(float(np.quantile(v, 0.5)), 6),
                    "p95": round(float(np.quantile(v, 0.95)), 6), "mean": round(float(np.mean(v)), 6)}
                for a, v in sorted(draws.items())}


# --------------------------------------------------------------------------------------
# validation helpers (synthetic ground truth)
# --------------------------------------------------------------------------------------
def synthetic_truth(twin: CyberTwinGraph, *, seed: int = 0, spread: float = 0.6) -> Dict[str, float]:
    """Hidden 'true' per-route probabilities: heuristic x lognormal error (range only)."""
    rng = np.random.default_rng(seed)
    return {meta.route_id: float(min(0.95, max(0.002, twin.edges[eid].p * math.exp(rng.normal(0, spread)))))
            for eid, meta in sorted(twin.route_meta.items())}


def simulate_exercises(truth: Mapping[str, float], *, coverage: float = 0.6, seed: int = 0,
                       when: Optional[datetime] = None) -> List[Outcome]:
    rng = np.random.default_rng(seed)
    when = when or datetime.now(timezone.utc)
    out = []
    for rid, p in sorted(truth.items()):
        if rng.random() < coverage:
            n = int(rng.integers(5, 41))
            out.append(Outcome(rid, n, int(rng.binomial(n, p)), when, "exercise"))
    return out
