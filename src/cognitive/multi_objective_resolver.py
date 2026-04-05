"""
S3M Multi-Objective Resolver — Conflicting Goal Resolution
===========================================================
When survival, mission progress, ROE compliance, resource conservation,
and information gain conflict, this resolver builds Pareto-efficient
candidate actions and scalarizes them with a configurable strategy.
"""

from __future__ import annotations

import math
import threading
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:  # pragma: no cover - optional integration bridge
    from src.autonomy.decision_engine.multi_objective import ParetoOptimizer
except Exception:  # pragma: no cover - optional integration bridge
    ParetoOptimizer = None  # type: ignore[assignment]


class ResolutionStrategy(str, Enum):
    """Supported scalarization strategies for multi-objective resolution."""

    WEIGHTED_SUM = "weighted_sum"
    TOPSIS = "topsis"
    LEXICOGRAPHIC = "lexicographic"
    MINIMAX_REGRET = "minimax_regret"


class ObjectiveSpec(BaseModel):
    """Definition of one objective in the tactical optimization problem."""

    name: str
    weight: float = Field(default=0.2, ge=0.0, le=1.0)
    direction: str = "maximize"
    threshold: Optional[float] = None


class ConflictReport(BaseModel):
    """Detected conflict report between objective pairs."""

    objective_a: str
    objective_b: str
    correlation: float
    severity: str = "low"


class ParetoSolution(BaseModel):
    """One Pareto-optimal action and objective projection."""

    action: str
    scores: Dict[str, float] = Field(default_factory=dict)
    scalarized_value: float = 0.0
    rank: int = 1


class MultiObjectiveResolver:
    """
    Resolve action tradeoffs with Pareto + scalarization.

    The resolver is deterministic and intentionally lightweight for edge
    deployment in constrained compute environments.
    """

    def __init__(
        self,
        objectives: Optional[List[ObjectiveSpec]] = None,
        strategy: ResolutionStrategy = ResolutionStrategy.TOPSIS,
    ) -> None:
        """Initialize objective definitions and scalarization strategy."""
        self._objectives = objectives or [
            ObjectiveSpec(name="survival", weight=0.35, direction="maximize"),
            ObjectiveSpec(name="mission_progress", weight=0.25, direction="maximize"),
            ObjectiveSpec(name="roe_compliance", weight=0.20, direction="maximize"),
            ObjectiveSpec(name="resource_efficiency", weight=0.10, direction="maximize"),
            ObjectiveSpec(name="information_gain", weight=0.10, direction="maximize"),
        ]
        self._strategy = strategy
        self._lock = threading.RLock()
        self._pareto_optimizer = ParetoOptimizer() if ParetoOptimizer is not None else None

    def resolve(
        self,
        q_values: Dict[str, float],
        objectives: Dict[str, float],
        belief: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve objective conflicts and return adjusted Q-values.

        Returns a dictionary with:
          - `adjusted_q`: scalarized action value map
          - `conflicts`: list of objective name pairs with negative correlation
          - `pareto_front`: list of non-dominated action names
          - `strategy_used`: scalarization strategy actually applied
        """
        if not q_values:
            return {
                "adjusted_q": {},
                "conflicts": [],
                "pareto_front": [],
                "strategy_used": "none",
            }

        with self._lock:
            action_objectives = self._estimate_objective_scores(q_values, objectives, belief)
            conflicts = self._detect_conflicts(action_objectives)
            pareto_actions = self._pareto_front(action_objectives)

            if self._strategy == ResolutionStrategy.TOPSIS:
                adjusted = self._topsis(action_objectives)
            elif self._strategy == ResolutionStrategy.LEXICOGRAPHIC:
                adjusted = self._lexicographic(action_objectives)
            elif self._strategy == ResolutionStrategy.MINIMAX_REGRET:
                adjusted = self._minimax_regret(action_objectives)
            else:
                adjusted = self._weighted_sum(action_objectives)

            if belief:
                entropy = -sum(prob * math.log(prob + 1e-30) for prob in belief.values() if prob > 0)
                max_entropy = math.log(max(len(belief), 1))
                uncertainty_factor = 1.0 - 0.3 * (entropy / max_entropy if max_entropy > 0 else 0.0)
                adjusted = {action: value * uncertainty_factor for action, value in adjusted.items()}

            return {
                "adjusted_q": adjusted,
                "conflicts": conflicts,
                "pareto_front": pareto_actions,
                "strategy_used": self._strategy.value,
            }

    def _estimate_objective_scores(
        self,
        q_values: Dict[str, float],
        objectives: Dict[str, float],
        belief: Optional[Dict[str, float]],
    ) -> Dict[str, Dict[str, float]]:
        """Estimate objective scores per action with tactical heuristics."""
        result: Dict[str, Dict[str, float]] = {}
        q_max = max((abs(value) for value in q_values.values()), default=1.0)
        q_max = max(q_max, 1e-6)

        for action, q_value in q_values.items():
            q_norm = q_value / q_max
            base = (q_norm + 1.0) / 2.0
            scores: Dict[str, float] = {}
            for spec in self._objectives:
                _obj_weight = objectives.get(spec.name, spec.weight)
                score = base

                if spec.name == "survival":
                    if action in ("retreat", "evade"):
                        score = min(1.0, base + 0.3)
                    elif action == "engage":
                        score = max(0.0, base - 0.2)
                elif spec.name == "mission_progress":
                    if action in ("advance", "engage", "recon"):
                        score = min(1.0, base + 0.2)
                    elif action in ("retreat", "hold"):
                        score = max(0.0, base - 0.15)
                elif spec.name == "roe_compliance":
                    if action == "engage":
                        score = max(0.0, base - 0.3)
                    else:
                        score = min(1.0, base + 0.1)
                elif spec.name == "information_gain":
                    if action == "recon":
                        score = min(1.0, base + 0.4)
                    else:
                        score = base * 0.7

                if belief and spec.name == "survival":
                    uncertain_bonus = 1.0 - max(belief.values(), default=0.0)
                    score = min(1.0, score + 0.1 * uncertain_bonus)

                scores[spec.name] = max(0.0, min(1.0, score))
            result[action] = scores
        return result

    def _detect_conflicts(self, action_objectives: Dict[str, Dict[str, float]]) -> List[Tuple[str, str]]:
        """Detect objective conflicts using pairwise rank correlation across actions."""
        conflicts: List[Tuple[str, str]] = []
        objective_names = [spec.name for spec in self._objectives]
        actions = list(action_objectives.keys())
        if len(actions) < 2:
            return conflicts

        for index, objective_a in enumerate(objective_names):
            for objective_b in objective_names[index + 1 :]:
                values_a = [action_objectives[action].get(objective_a, 0.0) for action in actions]
                values_b = [action_objectives[action].get(objective_b, 0.0) for action in actions]
                correlation = self._rank_correlation(values_a, values_b)
                if correlation < -0.3:
                    conflicts.append((objective_a, objective_b))
        return conflicts

    @staticmethod
    def _rank_correlation(values_a: List[float], values_b: List[float]) -> float:
        """Compute Spearman correlation using stable positional ranking."""
        n_items = len(values_a)
        if n_items < 2 or len(values_b) != n_items:
            return 0.0

        ranks_a = MultiObjectiveResolver._to_ranks(values_a)
        ranks_b = MultiObjectiveResolver._to_ranks(values_b)
        d_squared = sum((ra - rb) ** 2 for ra, rb in zip(ranks_a, ranks_b))
        denominator = n_items * (n_items**2 - 1)
        return 1.0 - (6.0 * d_squared / denominator) if denominator > 0 else 0.0

    @staticmethod
    def _to_ranks(values: List[float]) -> List[int]:
        """Return deterministic ranks for a list of values."""
        sorted_indices = sorted(range(len(values)), key=lambda idx: values[idx])
        rank_map = {idx: rank for rank, idx in enumerate(sorted_indices)}
        return [rank_map[idx] for idx in range(len(values))]

    def _pareto_front(self, action_objectives: Dict[str, Dict[str, float]]) -> List[str]:
        """Return non-dominated actions from objective vectors."""
        if self._pareto_optimizer is not None:
            vectors = {action: dict(scores) for action, scores in action_objectives.items()}
            try:
                external_frontier = self._pareto_optimizer.pareto_frontier(vectors)
                if external_frontier:
                    return [str(name) for name in external_frontier]
            except Exception:
                pass

        actions = list(action_objectives.keys())
        dominated = set()
        for i, action_a in enumerate(actions):
            for j, action_b in enumerate(actions):
                if i == j:
                    continue
                if self._dominates(action_objectives[action_b], action_objectives[action_a]):
                    dominated.add(action_a)
                    break
        return [action for action in actions if action not in dominated]

    def _dominates(self, candidate_a: Dict[str, float], candidate_b: Dict[str, float]) -> bool:
        """Check whether objective vector A Pareto-dominates vector B."""
        strictly_better = False
        for spec in self._objectives:
            value_a = candidate_a.get(spec.name, 0.0)
            value_b = candidate_b.get(spec.name, 0.0)
            if spec.direction == "minimize":
                value_a, value_b = -value_a, -value_b
            if value_a < value_b:
                return False
            if value_a > value_b:
                strictly_better = True
        return strictly_better

    def _weighted_sum(self, action_objectives: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Compute weighted-sum scalarization for each action."""
        results: Dict[str, float] = {}
        for action, scores in action_objectives.items():
            results[action] = sum(
                scores.get(spec.name, 0.0) * self._weight_for(spec.name) for spec in self._objectives
            )
        return results

    def _topsis(self, action_objectives: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Compute TOPSIS closeness to ideal objective vector."""
        objective_names = [spec.name for spec in self._objectives]
        actions = list(action_objectives.keys())
        if not actions:
            return {}

        ideal: Dict[str, float] = {}
        anti_ideal: Dict[str, float] = {}
        for objective in objective_names:
            values = [action_objectives[action].get(objective, 0.0) for action in actions]
            ideal[objective] = max(values)
            anti_ideal[objective] = min(values)

        scores: Dict[str, float] = {}
        for action in actions:
            d_ideal = math.sqrt(
                sum(
                    ((action_objectives[action].get(objective, 0.0) - ideal[objective]) ** 2)
                    * (self._weight_for(objective) ** 2)
                    for objective in objective_names
                )
            )
            d_anti = math.sqrt(
                sum(
                    ((action_objectives[action].get(objective, 0.0) - anti_ideal[objective]) ** 2)
                    * (self._weight_for(objective) ** 2)
                    for objective in objective_names
                )
            )
            denominator = d_ideal + d_anti
            scores[action] = d_anti / denominator if denominator > 1e-12 else 0.5
        return scores

    def _lexicographic(self, action_objectives: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Compute lexicographic score using descending objective priority."""
        sorted_objectives = sorted(self._objectives, key=lambda spec: spec.weight, reverse=True)
        actions = list(action_objectives.keys())
        scores = {action: 0.0 for action in actions}
        multiplier = 1.0
        for spec in sorted_objectives:
            for action in actions:
                scores[action] += multiplier * action_objectives[action].get(spec.name, 0.0)
            multiplier *= 0.1
        return scores

    def _minimax_regret(self, action_objectives: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Compute minimax-regret utility where higher value is better."""
        objective_names = [spec.name for spec in self._objectives]
        actions = list(action_objectives.keys())
        best_per_objective = {
            objective: max(action_objectives[action].get(objective, 0.0) for action in actions)
            for objective in objective_names
        }

        scores: Dict[str, float] = {}
        for action in actions:
            max_regret = max(
                (best_per_objective[objective] - action_objectives[action].get(objective, 0.0))
                * self._weight_for(objective)
                for objective in objective_names
            )
            scores[action] = 1.0 - max_regret
        return scores

    def _weight_for(self, objective_name: str) -> float:
        """Return configured objective weight; defaults to a low prior weight."""
        for spec in self._objectives:
            if spec.name == objective_name:
                return spec.weight
        return 0.1
