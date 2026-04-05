"""
S3M game-theoretic coordination layer for tactical swarms.

Provides Nash-style strategy stabilization when agents compete over limited
resources or overlapping objective regions.
"""

from __future__ import annotations

from itertools import product as itertools_product
import logging
import random
from typing import Any, Dict, List, Optional

from src.autonomy.arbitration.coalition_engine import CoalitionEngine


LOGGER = logging.getLogger(__name__)


class GameTheoreticLayer:
    """
    Nash-equilibrium approximations for multi-agent strategic coordination.

    Tactical context: strategy stabilization helps prevent oscillatory task
    switching when multiple autonomous assets can satisfy the same objective.
    """

    def __init__(
        self,
        max_iterations: int = 200,
        seed: Optional[int] = None,
        coalition_engine: Optional[CoalitionEngine] = None,
    ) -> None:
        self._max_iter = max(10, int(max_iterations))
        self._rng = random.Random(seed)
        self._coalition_engine = coalition_engine or CoalitionEngine(mc_samples=500)

    @staticmethod
    def _profile_key(agents: List[str], profile: Dict[str, str]) -> str:
        return "|".join(f"{agent}:{profile.get(agent, 'default')}" for agent in agents)

    @staticmethod
    def _log_bilingual(message_en: str, message_ar: str, **payload: Any) -> None:
        LOGGER.info("%s | %s | payload=%s", message_en, message_ar, payload)

    def build_payoff_matrix(
        self,
        agents: List[str],
        actions: Dict[str, List[str]],
        utility_fn: Any,
    ) -> Dict[str, Dict[str, float]]:
        """
        Build payoff matrix from utility callback.

        utility_fn(agent_id, agent_action, all_actions_dict) -> float
        """
        if not agents:
            return {}
        if len(agents) > 3:
            return self._sample_payoffs(agents, actions, utility_fn, samples=500)

        action_lists = [actions.get(agent, ["default"]) for agent in agents]
        payoffs: Dict[str, Dict[str, float]] = {agent: {} for agent in agents}
        for combo in itertools_product(*action_lists):
            action_profile = {agents[idx]: combo[idx] for idx in range(len(agents))}
            profile_key = self._profile_key(agents, action_profile)
            for agent in agents:
                val = float(utility_fn(agent, action_profile[agent], action_profile))
                payoffs[agent][profile_key] = val
        return payoffs

    def _sample_payoffs(
        self,
        agents: List[str],
        actions: Dict[str, List[str]],
        utility_fn: Any,
        samples: int = 500,
    ) -> Dict[str, Dict[str, float]]:
        payoffs: Dict[str, Dict[str, float]] = {agent: {} for agent in agents}
        for _ in range(max(1, int(samples))):
            profile = {agent: self._rng.choice(actions.get(agent, ["default"])) for agent in agents}
            key = self._profile_key(agents, profile)
            for agent in agents:
                payoffs[agent][key] = float(utility_fn(agent, profile[agent], profile))
        return payoffs

    def find_nash_equilibrium(
        self,
        agents: List[str],
        actions: Dict[str, List[str]],
        payoffs: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """Approximate pure-strategy Nash via iterated best response."""
        if not agents:
            return {"equilibrium": {}, "stable": True, "iterations": 0, "payoff_profile": {}}

        current = {agent: self._rng.choice(actions.get(agent, ["default"])) for agent in agents}
        stable = False
        iteration_count = 0

        for iteration in range(self._max_iter):
            iteration_count = iteration + 1
            changed = False
            for agent in agents:
                best_action = current[agent]
                best_payoff = float("-inf")
                for candidate in actions.get(agent, ["default"]):
                    candidate_profile = dict(current)
                    candidate_profile[agent] = candidate
                    key = self._profile_key(agents, candidate_profile)
                    payoff = float(payoffs.get(agent, {}).get(key, 0.0))
                    if payoff > best_payoff:
                        best_payoff = payoff
                        best_action = candidate
                if best_action != current[agent]:
                    current[agent] = best_action
                    changed = True
            if not changed:
                stable = True
                break

        final_key = self._profile_key(agents, current)
        payoff_profile = {agent: float(payoffs.get(agent, {}).get(final_key, 0.0)) for agent in agents}
        self._log_bilingual(
            "Nash search completed",
            "اكتمل البحث عن توازن ناش",
            stable=stable,
            iterations=iteration_count,
        )
        return {
            "equilibrium": dict(current),
            "stable": stable,
            "iterations": iteration_count,
            "payoff_profile": payoff_profile,
        }

    def fictitious_play(
        self,
        agents: List[str],
        actions: Dict[str, List[str]],
        utility_fn: Any,
        rounds: int = 100,
    ) -> Dict[str, Dict[str, float]]:
        """Approximate mixed strategies with fictitious play."""
        if not agents:
            return {}

        counts: Dict[str, Dict[str, int]] = {
            agent: {act: 0 for act in actions.get(agent, ["default"])} for agent in agents
        }
        current = {agent: self._rng.choice(actions.get(agent, ["default"])) for agent in agents}

        for _ in range(max(1, int(rounds))):
            for agent in agents:
                counts[agent][current[agent]] += 1
            for agent in agents:
                best_action = current[agent]
                best_expected = float("-inf")
                for candidate in actions.get(agent, ["default"]):
                    candidate_profile = dict(current)
                    candidate_profile[agent] = candidate
                    expected_payoff = float(utility_fn(agent, candidate, candidate_profile))
                    if expected_payoff > best_expected:
                        best_expected = expected_payoff
                        best_action = candidate
                current[agent] = best_action

        mixed: Dict[str, Dict[str, float]] = {}
        for agent in agents:
            total = sum(counts[agent].values()) or 1
            mixed[agent] = {action: cnt / total for action, cnt in counts[agent].items()}
        return mixed

    def cooperative_values(self, agents: List[str], objectives: List[str]) -> Dict[str, float]:
        """Compute cooperative value estimates via coalition-engine Shapley approximation."""
        value_fn = lambda coalition: float(min(len(coalition), len(objectives)) + 0.1 * len(coalition))
        return self._coalition_engine.approximate_shapley(players=agents, value_fn=value_fn)

    def coordinate_with_arbitrator(
        self,
        mission: Dict[str, Any],
        agents: List[Any],
        arbitrator: Any,
        mode: str = "coalition",
    ) -> Dict[str, Any]:
        """
        Build strategic equilibrium around arbitrator outputs.

        Tactical context: this adapter cross-checks arbitration assignments for
        strategic stability before mission execution starts.
        """
        arbitration = arbitrator.arbitrate(mission=mission, agents=agents, mode=mode)
        agent_ids = [str(getattr(agent, "agent_id", agent)) for agent in agents]
        base_assignments = dict(arbitration.get("assignments", {}))
        actions = {agent: [base_assignments.get(agent, "reserve"), "reserve"] for agent in agent_ids}

        def utility(agent_id: str, action: str, profile: Dict[str, str]) -> float:
            base = 1.0 if action == base_assignments.get(agent_id, "reserve") else 0.6
            congestion = sum(1 for _, choice in profile.items() if choice == action)
            return base - (0.1 * max(0, congestion - 1))

        payoffs = self.build_payoff_matrix(agent_ids, actions, utility)
        equilibrium = self.find_nash_equilibrium(agent_ids, actions, payoffs)
        return {
            "arbitration": arbitration,
            "equilibrium": equilibrium,
            "rationale_en": "Nash layer computed stability for arbitration assignment profile.",
            "rationale_ar": "قامت طبقة ناش بحساب الاستقرار لملف تعيينات التحكيم.",
        }
