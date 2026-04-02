"""Multi-objective tactical action scoring with Pareto selection.

This optimizer balances survivability, mission progress, legal/ROE risk, fuel,
and information gain so no single metric dominates battlefield behavior.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


OBJECTIVES = ("survival", "mission_progress", "roe_risk", "fuel_cost", "info_gain")
MAXIMIZE = {"survival", "mission_progress", "info_gain"}
MINIMIZE = {"roe_risk", "fuel_cost"}


class ParetoOptimizer:
    """Finds Pareto-efficient actions and ranks them by scalarization."""

    def __init__(self, weights: Dict[str, float] | None = None) -> None:
        base = {
            "survival": 0.35,
            "mission_progress": 0.25,
            "roe_risk": 0.2,
            "fuel_cost": 0.1,
            "info_gain": 0.1,
        }
        if weights:
            for key, value in weights.items():
                if key in base:
                    base[key] = max(0.0, float(value))
        total = sum(base.values()) or 1.0
        self.weights = {k: v / total for k, v in base.items()}

    def _normalize_scores(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranges: Dict[str, Tuple[float, float]] = {}
        for obj in OBJECTIVES:
            vals = [float(c["objectives"].get(obj, 0.0)) for c in candidates]
            lo, hi = min(vals), max(vals)
            ranges[obj] = (lo, hi)

        normalized: List[Dict[str, Any]] = []
        for c in candidates:
            n_obj: Dict[str, float] = {}
            for obj in OBJECTIVES:
                val = float(c["objectives"].get(obj, 0.0))
                lo, hi = ranges[obj]
                if abs(hi - lo) < 1e-9:
                    score = 1.0
                else:
                    if obj in MAXIMIZE:
                        score = (val - lo) / (hi - lo)
                    else:
                        score = (hi - val) / (hi - lo)
                n_obj[obj] = max(0.0, min(1.0, score))
            out = dict(c)
            out["normalized_objectives"] = n_obj
            normalized.append(out)
        return normalized

    def _dominates(self, a: Dict[str, float], b: Dict[str, float]) -> bool:
        at_least_as_good = True
        strictly_better = False
        for obj in OBJECTIVES:
            if a[obj] < b[obj]:
                at_least_as_good = False
                break
            if a[obj] > b[obj]:
                strictly_better = True
        return at_least_as_good and strictly_better

    def pareto_frontier(self, vectors: Dict[str, Dict[str, float]]) -> List[str]:
        """Return non-dominated action names for candidate objective vectors."""
        if not vectors:
            return []
        candidates = [{"action": a, "objectives": obj} for a, obj in vectors.items()]
        normalized = self._normalize_scores(candidates)
        frontier: List[str] = []
        for i, candidate in enumerate(normalized):
            dominated = False
            for j, other in enumerate(normalized):
                if i == j:
                    continue
                if self._dominates(other["normalized_objectives"], candidate["normalized_objectives"]):
                    dominated = True
                    break
            if not dominated:
                frontier.append(str(candidate["action"]))
        return frontier

    def _weighted_sum(self, candidate: Dict[str, Any]) -> float:
        n_obj = candidate["normalized_objectives"]
        return float(sum(self.weights[obj] * float(n_obj[obj]) for obj in OBJECTIVES))

    def _chebyshev(self, candidate: Dict[str, Any]) -> float:
        n_obj = candidate["normalized_objectives"]
        worst = max(self.weights[obj] * abs(1.0 - float(n_obj[obj])) for obj in OBJECTIVES)
        return float(1.0 - worst)

    def _topsis_rank(self, candidates: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
        weighted = []
        for c in candidates:
            n_obj = c["normalized_objectives"]
            vec = {obj: self.weights[obj] * float(n_obj[obj]) for obj in OBJECTIVES}
            weighted.append((c, vec))

        ideal = {obj: max(v[obj] for _, v in weighted) for obj in OBJECTIVES}
        nadir = {obj: min(v[obj] for _, v in weighted) for obj in OBJECTIVES}
        ranked: List[Tuple[Dict[str, Any], float]] = []
        for c, vec in weighted:
            d_pos = math.sqrt(sum((vec[obj] - ideal[obj]) ** 2 for obj in OBJECTIVES))
            d_neg = math.sqrt(sum((vec[obj] - nadir[obj]) ** 2 for obj in OBJECTIVES))
            closeness = d_neg / max(d_pos + d_neg, 1e-9)
            ranked.append((c, float(closeness)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def select_action(
        self,
        vectors: Dict[str, Dict[str, float]],
        method: str = "topsis",
        fallback: str = "hold",
    ) -> Tuple[str, float, Dict[str, Any]]:
        """Select one action using Pareto + scalarization strategy."""
        if not vectors:
            return fallback, 0.0, {"method": method, "reason": "no_candidates"}

        frontier_names = self.pareto_frontier(vectors)
        frontier_candidates = [
            {"action": name, "objectives": vectors[name]}
            for name in frontier_names
            if name in vectors
        ]
        normalized = self._normalize_scores(frontier_candidates)
        if not normalized:
            return fallback, 0.0, {"method": method, "reason": "empty_frontier"}

        method_norm = str(method).lower().strip()
        scores: Dict[str, float] = {}
        if method_norm == "weighted_sum":
            for c in normalized:
                scores[str(c["action"])] = self._weighted_sum(c)
        elif method_norm == "chebyshev":
            for c in normalized:
                scores[str(c["action"])] = self._chebyshev(c)
        else:
            ranking = self._topsis_rank(normalized)
            for c, score in ranking:
                scores[str(c["action"])] = float(score)
            method_norm = "topsis"

        best_action = max(scores.items(), key=lambda item: item[1])[0]
        best_score = float(scores[best_action])
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        runner_up = ordered[1][0] if len(ordered) > 1 else None

        return (
            best_action,
            best_score,
            {
                "method": method_norm,
                "frontier": frontier_names,
                "tradeoff": {
                    "winner": best_action,
                    "runner_up": runner_up,
                },
                "scores": dict(scores),
            },
        )

