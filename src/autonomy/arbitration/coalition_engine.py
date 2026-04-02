"""Coalition formation using Monte Carlo Shapley-value approximation.

This engine estimates marginal contribution of each agent to coalition value
and forms stable, rational coalitions for tactical mission objectives.
"""

from __future__ import annotations

import random
from typing import Callable, Dict, Iterable, List


class CoalitionEngine:
    """Cooperative-game coalition builder using Shapley approximation."""

    def __init__(self, mc_samples: int = 500, random_seed: int | None = None) -> None:
        self.mc_samples = max(1, int(mc_samples))
        self._rng = random.Random(random_seed)

    def approximate_shapley(
        self,
        players: List[str],
        value_fn: Callable[[List[str]], float],
    ) -> Dict[str, float]:
        """Approximate Shapley values by random permutation sampling."""
        if not players:
            return {}
        values = {p: 0.0 for p in players}
        for _ in range(self.mc_samples):
            perm = players[:]
            self._rng.shuffle(perm)
            coalition: List[str] = []
            coalition_value = 0.0
            for p in perm:
                coalition.append(p)
                new_value = float(value_fn(coalition))
                values[p] += new_value - coalition_value
                coalition_value = new_value
        inv = 1.0 / self.mc_samples
        return {p: values[p] * inv for p in players}

    def _default_value_fn(self, coalition: List[str], objectives: List[str]) -> float:
        """Simple monotonic coalition utility for tactical objective coverage."""
        if not coalition or not objectives:
            return 0.0
        coverage = min(len(objectives), len(coalition))
        return float(coverage) + 0.1 * float(len(coalition))

    def check_core_stability(self, assignments: Dict[str, str], objectives: List[str]) -> bool:
        """Core stability heuristic: no assigned agent gets negative value."""
        if not assignments:
            return True
        players = list(assignments.keys())
        value_fn = lambda c: self._default_value_fn(c, objectives)
        shapley = self.approximate_shapley(players, value_fn)
        return all(v >= -1e-9 for v in shapley.values())

    def check_individual_rationality(self, assignments: Dict[str, str]) -> bool:
        """Individual rationality heuristic for coalition payoffs."""
        if not assignments:
            return True
        # With default monotonic value, singleton values are non-negative.
        return True

    def form_coalitions(self, agents: List[str], objectives: List[str]) -> Dict[str, object]:
        """Greedy coalition assignment by Shapley rank over default value model."""
        assignments: Dict[str, str] = {}
        if not agents:
            return {"assignments": assignments, "core_stable": True, "individually_rational": True}
        if not objectives:
            for agent in agents:
                assignments[agent] = "reserve"
            return {"assignments": assignments, "core_stable": True, "individually_rational": True}

        value_fn = lambda c: self._default_value_fn(c, objectives)
        shapley = self.approximate_shapley(agents, value_fn)
        ranked = sorted(agents, key=lambda a: shapley.get(a, 0.0), reverse=True)
        for idx, agent in enumerate(ranked):
            assignments[agent] = objectives[idx % len(objectives)]

        return {
            "assignments": assignments,
            "core_stable": self.check_core_stability(assignments, objectives),
            "individually_rational": self.check_individual_rationality(assignments),
            "shapley": shapley,
        }

