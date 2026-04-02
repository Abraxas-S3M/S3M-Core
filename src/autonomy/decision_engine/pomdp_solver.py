"""Point-based POMDP solver for tactical decision support.

The solver approximates optimal policies over partially observed combat states
using edge-safe point-based value iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple


TACTICAL_STATES: Tuple[str, ...] = (
    "safe",
    "threatened",
    "engaged",
    "mission_complete",
    "destroyed",
)

TACTICAL_ACTIONS: Tuple[str, ...] = (
    "advance",
    "hold",
    "retreat",
    "engage",
    "evade",
    "recon",
)

TACTICAL_OBSERVATIONS: Tuple[str, ...] = (
    "clear",
    "threat_detected",
    "under_fire",
    "objective_secured",
    "catastrophic_loss",
)


@dataclass
class _AlphaVector:
    action: str
    values: Dict[str, float]


class POMDPSolver:
    """Point-Based Value Iteration with online belief/action interfaces."""

    def __init__(self, discount: float = 0.95, horizon: int = 8) -> None:
        self.discount = max(0.0, min(0.999, float(discount)))
        self.horizon = max(1, int(horizon))
        self.states = list(TACTICAL_STATES)
        self.actions = list(TACTICAL_ACTIONS)
        self.observations = list(TACTICAL_OBSERVATIONS)
        self.transition = self._build_transition_model()
        self.observation_model = self._build_observation_model()
        self.reward = self._build_reward_model()
        self._belief: Dict[str, float] = {s: 1.0 / len(self.states) for s in self.states}
        self._alpha_vectors: List[_AlphaVector] = []

    def _normalize(self, distribution: Dict[str, float]) -> Dict[str, float]:
        total = sum(max(0.0, float(v)) for v in distribution.values())
        if total <= 0.0:
            uniform = 1.0 / len(distribution)
            return {k: uniform for k in distribution}
        return {k: max(0.0, float(v)) / total for k, v in distribution.items()}

    def _build_transition_model(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        t: Dict[str, Dict[str, Dict[str, float]]] = {}
        for state in self.states:
            t[state] = {}
            for action in self.actions:
                base = {s: 0.0 for s in self.states}
                if state == "destroyed":
                    base["destroyed"] = 1.0
                elif state == "mission_complete":
                    base["mission_complete"] = 0.95
                    base["safe"] = 0.05
                elif state == "safe":
                    if action == "advance":
                        base["safe"] = 0.58
                        base["threatened"] = 0.28
                        base["mission_complete"] = 0.14
                    elif action == "recon":
                        base["safe"] = 0.72
                        base["threatened"] = 0.20
                        base["mission_complete"] = 0.08
                    elif action in {"retreat", "evade"}:
                        base["safe"] = 0.85
                        base["threatened"] = 0.12
                        base["engaged"] = 0.03
                    elif action == "engage":
                        base["threatened"] = 0.46
                        base["safe"] = 0.44
                        base["destroyed"] = 0.10
                    else:
                        base["safe"] = 0.80
                        base["threatened"] = 0.20
                elif state == "threatened":
                    if action == "engage":
                        base["engaged"] = 0.56
                        base["safe"] = 0.20
                        base["destroyed"] = 0.24
                    elif action in {"retreat", "evade"}:
                        base["safe"] = 0.57
                        base["threatened"] = 0.33
                        base["engaged"] = 0.10
                    elif action == "recon":
                        base["threatened"] = 0.66
                        base["engaged"] = 0.20
                        base["safe"] = 0.14
                    else:
                        base["threatened"] = 0.56
                        base["engaged"] = 0.28
                        base["safe"] = 0.11
                        base["destroyed"] = 0.05
                else:  # engaged
                    if action == "engage":
                        base["engaged"] = 0.45
                        base["safe"] = 0.15
                        base["mission_complete"] = 0.25
                        base["destroyed"] = 0.15
                    elif action in {"retreat", "evade"}:
                        base["threatened"] = 0.50
                        base["safe"] = 0.20
                        base["engaged"] = 0.20
                        base["destroyed"] = 0.10
                    else:
                        base["engaged"] = 0.52
                        base["threatened"] = 0.24
                        base["destroyed"] = 0.24
                t[state][action] = self._normalize(base)
        return t

    def _build_observation_model(self) -> Dict[str, Dict[str, float]]:
        return {
            "safe": self._normalize(
                {
                    "clear": 0.76,
                    "threat_detected": 0.17,
                    "under_fire": 0.03,
                    "objective_secured": 0.03,
                    "catastrophic_loss": 0.01,
                }
            ),
            "threatened": self._normalize(
                {
                    "clear": 0.14,
                    "threat_detected": 0.61,
                    "under_fire": 0.15,
                    "objective_secured": 0.06,
                    "catastrophic_loss": 0.04,
                }
            ),
            "engaged": self._normalize(
                {
                    "clear": 0.05,
                    "threat_detected": 0.20,
                    "under_fire": 0.60,
                    "objective_secured": 0.05,
                    "catastrophic_loss": 0.10,
                }
            ),
            "mission_complete": self._normalize(
                {
                    "clear": 0.18,
                    "threat_detected": 0.05,
                    "under_fire": 0.02,
                    "objective_secured": 0.74,
                    "catastrophic_loss": 0.01,
                }
            ),
            "destroyed": self._normalize(
                {
                    "clear": 0.01,
                    "threat_detected": 0.02,
                    "under_fire": 0.10,
                    "objective_secured": 0.00,
                    "catastrophic_loss": 0.87,
                }
            ),
        }

    def _build_reward_model(self) -> Dict[str, Dict[str, float]]:
        rewards: Dict[str, Dict[str, float]] = {s: {} for s in self.states}
        for state in self.states:
            for action in self.actions:
                value = -1.0
                if state == "destroyed":
                    value = -100.0
                elif state == "mission_complete":
                    value = 40.0 if action in {"hold", "recon"} else 25.0
                elif state == "safe":
                    if action == "advance":
                        value = 8.0
                    elif action == "recon":
                        value = 4.0
                    elif action == "engage":
                        value = -2.0
                    elif action in {"retreat", "evade"}:
                        value = -1.0
                    else:
                        value = 2.0
                elif state == "threatened":
                    if action in {"retreat", "evade"}:
                        value = 6.0
                    elif action == "engage":
                        value = 2.0
                    elif action == "recon":
                        value = 1.5
                    else:
                        value = -1.5
                else:  # engaged
                    if action == "engage":
                        value = 6.0
                    elif action in {"evade", "retreat"}:
                        value = 4.0
                    else:
                        value = -3.0
                rewards[state][action] = value
        return rewards

    def _belief_points(self) -> List[Dict[str, float]]:
        points: List[Dict[str, float]] = []
        # Canonical tactical corner beliefs + mixed contingencies.
        for state in self.states:
            b = {s: 0.0 for s in self.states}
            b[state] = 1.0
            points.append(b)
        points.append(self._normalize({"safe": 0.5, "threatened": 0.5, "engaged": 0.0, "mission_complete": 0.0, "destroyed": 0.0}))
        points.append(self._normalize({"safe": 0.2, "threatened": 0.4, "engaged": 0.3, "mission_complete": 0.05, "destroyed": 0.05}))
        points.append(self._normalize(dict(self._belief)))
        return points

    def solve(self, iterations: int = 20) -> None:
        """Offline PBVI backups to compute compact alpha-vector policy."""
        points = self._belief_points()
        alpha: List[_AlphaVector] = [_AlphaVector(action="hold", values={s: 0.0 for s in self.states})]
        for _ in range(max(1, int(iterations))):
            next_alpha: List[_AlphaVector] = []
            for belief in points:
                best_action = "hold"
                best_values = {s: 0.0 for s in self.states}
                best_score = -float("inf")
                for action in self.actions:
                    candidate: Dict[str, float] = {}
                    for state in self.states:
                        immediate = self.reward[state][action]
                        continuation = 0.0
                        for next_state, p in self.transition[state][action].items():
                            best_next = max(vec.values.get(next_state, 0.0) for vec in alpha) if alpha else 0.0
                            continuation += p * best_next
                        candidate[state] = immediate + self.discount * continuation
                    score = sum(belief[s] * candidate[s] for s in self.states)
                    if score > best_score:
                        best_score = score
                        best_action = action
                        best_values = candidate
                next_alpha.append(_AlphaVector(action=best_action, values=best_values))
            alpha = next_alpha[:96] if len(next_alpha) > 96 else next_alpha
        self._alpha_vectors = alpha or [_AlphaVector(action="hold", values={s: 0.0 for s in self.states})]

    def get_belief(self) -> Dict[str, float]:
        return dict(self._belief)

    def set_belief(self, belief: Dict[str, float]) -> None:
        projected = {s: max(0.0, float(belief.get(s, 0.0))) for s in self.states}
        self._belief = self._normalize(projected)

    def belief_update(self, action: str, observation: str) -> Dict[str, float]:
        """Online Bayes belief update for one action-observation pair."""
        act = action if action in self.actions else "hold"
        obs = observation if observation in self.observations else "threat_detected"
        updated: Dict[str, float] = {}
        for next_state in self.states:
            trans_sum = 0.0
            for state in self.states:
                trans_sum += self.transition[state][act][next_state] * self._belief[state]
            updated[next_state] = self.observation_model[next_state][obs] * trans_sum
        self._belief = self._normalize(updated)
        return dict(self._belief)

    def action_distribution(self, belief: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        b = self._normalize(dict(self._belief if belief is None else belief))
        raw: Dict[str, float] = {}
        for action in self.actions:
            q = 0.0
            for state in self.states:
                immediate = self.reward[state][action]
                continuation = 0.0
                for next_state, p in self.transition[state][action].items():
                    best_next = max(vec.values.get(next_state, 0.0) for vec in self._alpha_vectors) if self._alpha_vectors else 0.0
                    continuation += p * best_next
                q += b[state] * (immediate + self.discount * continuation)
            raw[action] = q
        anchor = max(raw.values()) if raw else 0.0
        exps = {a: math.exp(v - anchor) for a, v in raw.items()}
        denom = sum(exps.values()) or 1.0
        return {a: exps[a] / denom for a in self.actions}

    def select_action(self, belief: Optional[Dict[str, float]] = None) -> str:
        distribution = self.action_distribution(belief)
        return max(distribution.items(), key=lambda item: item[1])[0] if distribution else "hold"
