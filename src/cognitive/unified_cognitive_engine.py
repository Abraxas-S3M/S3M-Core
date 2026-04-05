"""
S3M Unified Cognitive Engine — POMDP-Based Central Decision Authority
======================================================================
This is the BRAIN of S3M. It replaces distributed rule-based + RL fallback
logic with a single, principled cognitive architecture that:

1. Maintains a Bayesian world model (uncertainty tracking)
2. Reasons under partial observability (POMDP belief updates)
3. Resolves conflicting objectives (multi-objective optimization)
4. Consults episodic/semantic memory for context
5. Produces auditable, bilingual decision records

Cognitive Cycle (per tick):
  PERCEIVE → UPDATE_WORLD_MODEL → REASON → DECIDE → ACT → REMEMBER

This engine is CPU-native and designed for edge deployment.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class CognitiveMode(str, Enum):
    """Operating mode of the cognitive engine."""

    DELIBERATE = "deliberate"
    REACTIVE = "reactive"
    REFLECTIVE = "reflective"
    DEGRADED = "degraded"


class CognitiveConfig(BaseModel):
    """Immutable configuration for the cognitive engine."""

    model_config = ConfigDict(frozen=True)

    max_hypotheses: int = Field(default=32, ge=4, le=256)
    belief_convergence_threshold: float = Field(default=0.85, ge=0.5, le=0.99)
    uncertainty_escalation_threshold: float = Field(default=0.7, ge=0.1, le=0.95)
    max_think_time_ms: float = Field(default=500.0, gt=0.0)
    discount_factor: float = Field(default=0.95, ge=0.5, le=0.999)
    planning_horizon: int = Field(default=8, ge=1, le=50)
    memory_query_limit: int = Field(default=5, ge=0, le=50)
    require_human_review_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    enable_memory_consultation: bool = True
    enable_multi_objective: bool = True
    enable_counterfactual: bool = True
    max_cycle_history: int = Field(default=1000, ge=10)


class CognitiveState(BaseModel):
    """Snapshot of the engine internals at one point in time."""

    model_config = ConfigDict(frozen=True)

    state_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: CognitiveMode = CognitiveMode.DELIBERATE
    world_entropy: float = 0.0
    belief_concentration: float = 0.5
    active_objectives: List[str] = Field(default_factory=list)
    conflicting_objectives: List[Tuple[str, str]] = Field(default_factory=list)
    dominant_hypothesis: Optional[str] = None
    dominant_confidence: float = 0.0
    memory_hits: int = 0
    think_time_ms: float = 0.0


class CognitiveDecision(BaseModel):
    """Output of one cognitive cycle — the chosen tactical action."""

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    selected_action: str
    action_parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    utility_score: float = 0.0
    rationale_en: str = ""
    rationale_ar: str = ""
    requires_human_review: bool = False
    supporting_evidence: List[str] = Field(default_factory=list)
    alternatives_considered: int = 0
    pareto_rank: int = 1
    belief_state_id: Optional[str] = None
    memory_context_ids: List[str] = Field(default_factory=list)
    counterfactual_notes: Optional[str] = None


class ThinkCycle(BaseModel):
    """Complete record of one cognitive cycle for deterministic audit."""

    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    state_before: Optional[CognitiveState] = None
    state_after: Optional[CognitiveState] = None
    decision: Optional[CognitiveDecision] = None
    observations_processed: int = 0
    world_model_updates: int = 0
    elapsed_ms: float = 0.0


class _BeliefTracker:
    """Log-space Bayesian belief distribution over world hypotheses."""

    LOG_FLOOR = -300.0

    def __init__(self, max_hypotheses: int = 32) -> None:
        self._max = max_hypotheses
        self._log_beliefs: Dict[str, float] = {}
        self._lock = threading.RLock()

    def initialize(self, hypotheses: Dict[str, float]) -> None:
        """Initialize the internal belief state from prior probabilities."""
        with self._lock:
            total = sum(max(1e-30, v) for v in hypotheses.values())
            self._log_beliefs = {
                h: max(self.LOG_FLOOR, math.log(max(1e-30, v) / total))
                for h, v in hypotheses.items()
            }
            self._prune()

    def update(self, likelihoods: Dict[str, float], source_weight: float = 1.0) -> None:
        """Apply one weighted Bayesian observation update in log-space."""
        with self._lock:
            if not self._log_beliefs:
                return
            w = max(0.01, min(1.0, source_weight))
            for hypothesis in self._log_beliefs:
                ll = likelihoods.get(hypothesis, 0.5)
                ll = max(1e-30, min(1.0 - 1e-10, ll))
                self._log_beliefs[hypothesis] += w * math.log(ll)
                self._log_beliefs[hypothesis] = max(
                    self.LOG_FLOOR, self._log_beliefs[hypothesis]
                )
            self._normalize()

    def _normalize(self) -> None:
        if not self._log_beliefs:
            return
        max_log = max(self._log_beliefs.values())
        exp_sum = sum(math.exp(value - max_log) for value in self._log_beliefs.values())
        log_norm = max_log + math.log(exp_sum) if exp_sum > 0 else 0.0
        for hypothesis in self._log_beliefs:
            self._log_beliefs[hypothesis] -= log_norm

    def _prune(self) -> None:
        if len(self._log_beliefs) > self._max:
            sorted_h = sorted(self._log_beliefs, key=self._log_beliefs.get, reverse=True)
            self._log_beliefs = {h: self._log_beliefs[h] for h in sorted_h[: self._max]}
            self._normalize()

    def distribution(self) -> Dict[str, float]:
        """Return normalized belief probabilities."""
        with self._lock:
            if not self._log_beliefs:
                return {}
            max_log = max(self._log_beliefs.values())
            raw = {h: math.exp(v - max_log) for h, v in self._log_beliefs.items()}
            total = sum(raw.values()) or 1.0
            return {h: raw[h] / total for h in raw}

    def entropy(self) -> float:
        """Return Shannon entropy over the current belief distribution."""
        dist = self.distribution()
        if not dist:
            return 0.0
        return -sum(prob * math.log(prob + 1e-30) for prob in dist.values())

    def max_hypothesis(self) -> Tuple[Optional[str], float]:
        """Return the highest-probability hypothesis and its confidence."""
        dist = self.distribution()
        if not dist:
            return None, 0.0
        best = max(dist, key=dist.get)
        return best, dist[best]

    def concentration(self) -> float:
        """Return normalized certainty, where 1.0 means highly concentrated beliefs."""
        dist = self.distribution()
        n = len(dist)
        if n <= 1:
            return 1.0
        entropy = self.entropy()
        max_entropy = math.log(n)
        return max(0.0, 1.0 - entropy / max_entropy) if max_entropy > 0 else 1.0


class _ActionValueEstimator:
    """Compute expected tactical utility for actions under belief uncertainty."""

    def __init__(self, discount: float = 0.95, horizon: int = 8) -> None:
        self.discount = discount
        self.horizon = horizon
        self._transition_cache: Dict[str, Dict[str, Dict[str, float]]] = {}
        self._reward_cache: Dict[str, Dict[str, float]] = {}

    def register_dynamics(
        self,
        transitions: Dict[str, Dict[str, Dict[str, float]]],
        rewards: Dict[str, Dict[str, float]],
    ) -> None:
        """Register transition/reward dynamics from tactical state models."""
        self._transition_cache = dict(transitions)
        self._reward_cache = dict(rewards)

    def q_values(self, belief: Dict[str, float], actions: List[str]) -> Dict[str, float]:
        """Compute one-step lookahead Q-values for each candidate action."""
        values: Dict[str, float] = {}
        states = list(belief.keys())
        for action in actions:
            action_value = 0.0
            for state in states:
                state_prob = belief.get(state, 0.0)
                if state_prob < 1e-12:
                    continue
                reward = self._reward_cache.get(state, {}).get(action, 0.0)
                continuation = 0.0
                transitions = self._transition_cache.get(state, {}).get(action, {})
                for next_state, trans_prob in transitions.items():
                    future_reward = (
                        max(self._reward_cache.get(next_state, {}).get(a, 0.0) for a in actions)
                        if actions
                        else 0.0
                    )
                    continuation += trans_prob * future_reward
                action_value += state_prob * (reward + self.discount * continuation)
            values[action] = action_value
        return values

    def best_action(self, belief: Dict[str, float], actions: List[str]) -> Tuple[str, float]:
        """Return the highest-value action and value under the current belief state."""
        q_values = self.q_values(belief, actions)
        if not q_values:
            return "hold", 0.0
        action = max(q_values, key=q_values.get)
        return action, q_values[action]


class UnifiedCognitiveEngine:
    """
    Central S3M cognitive authority for tactical decision making.

    This engine unifies belief tracking, world modeling, multi-objective
    optimization, and memory consultation into a single decision pathway.
    """

    def __init__(
        self,
        config: Optional[CognitiveConfig] = None,
        memory_store: Optional[Any] = None,
        world_model: Optional[Any] = None,
        objective_resolver: Optional[Any] = None,
    ) -> None:
        """Initialize the engine with optional memory/world-model integrations."""
        self.config = config or CognitiveConfig()
        self._belief = _BeliefTracker(max_hypotheses=self.config.max_hypotheses)
        self._estimator = _ActionValueEstimator(
            discount=self.config.discount_factor,
            horizon=self.config.planning_horizon,
        )
        self._memory = memory_store
        self._world_model = world_model
        self._resolver = objective_resolver
        self._actions: List[str] = []
        self._mode = CognitiveMode.DELIBERATE
        self._cycle_history: List[ThinkCycle] = []
        self._lock = threading.RLock()
        self._objectives: Dict[str, float] = {}
        self._roe_constraints: Dict[str, Any] = {}

    def initialize(self, hypotheses: Dict[str, float]) -> None:
        """Set the initial belief distribution over world hypotheses."""
        with self._lock:
            self._belief.initialize(hypotheses)

    def register_actions(self, actions: List[str]) -> None:
        """Register the available tactical actions for this mission context."""
        with self._lock:
            self._actions = list(actions) if actions else ["hold"]

    def register_dynamics(
        self,
        transitions: Dict[str, Dict[str, Dict[str, float]]],
        rewards: Dict[str, Dict[str, float]],
    ) -> None:
        """Register state transitions and rewards used by value estimation."""
        with self._lock:
            self._estimator.register_dynamics(transitions, rewards)

    def set_objectives(self, objectives: Dict[str, float]) -> None:
        """Set active mission objectives and their non-negative weights."""
        with self._lock:
            self._objectives = {k: max(0.0, float(v)) for k, v in objectives.items()}

    def set_roe(self, constraints: Dict[str, Any]) -> None:
        """Set rules-of-engagement constraints for tactical filtering."""
        with self._lock:
            self._roe_constraints = dict(constraints)

    def set_mode(self, mode: CognitiveMode) -> None:
        """Switch cognitive operating mode."""
        with self._lock:
            self._mode = mode

    def think(
        self,
        observations: List[Dict[str, Any]],
        objectives: Optional[Dict[str, float]] = None,
        roe_override: Optional[Dict[str, Any]] = None,
    ) -> ThinkCycle:
        """
        Execute one cognitive cycle: perceive, reason, decide, and audit.

        Parameters
        ----------
        observations:
            List of tactical observations. Each observation may include
            `hypothesis_likelihoods`, `source_weight`, and optional `raw_data`.
        objectives:
            Optional override for objective weights during this cycle.
        roe_override:
            Optional override for ROE constraints during this cycle.

        Returns
        -------
        ThinkCycle
            Full cycle record including pre/post state and chosen decision.
        """
        start = time.perf_counter()
        cycle = ThinkCycle()

        with self._lock:
            if objectives:
                self._objectives = {k: max(0.0, float(v)) for k, v in objectives.items()}
            if roe_override:
                self._roe_constraints = dict(roe_override)

            state_before = self._snapshot()
            cycle.state_before = state_before

            for obs in observations:
                likelihoods = obs.get("hypothesis_likelihoods", {})
                source_weight = float(obs.get("source_weight", 0.7))
                if likelihoods:
                    self._belief.update(likelihoods, source_weight)
                    cycle.world_model_updates += 1
                cycle.observations_processed += 1

            memory_context_ids: List[str] = []
            if self.config.enable_memory_consultation and self._memory:
                try:
                    dominant_h, _ = self._belief.max_hypothesis()
                    if dominant_h:
                        episodes = self._memory.query(
                            context=dominant_h,
                            limit=self.config.memory_query_limit,
                        )
                        memory_context_ids = [
                            str(ep.get("episode_id", "")) for ep in (episodes or [])
                        ]
                except Exception as exc:  # pragma: no cover - defensive integration guard
                    logger.warning("Memory consultation failed: %s", exc)

            belief_dist = self._belief.distribution()
            q_values = self._estimator.q_values(belief_dist, self._actions)

            conflicts: List[Tuple[str, str]] = []
            if self.config.enable_multi_objective and self._resolver and self._objectives:
                try:
                    resolution = self._resolver.resolve(
                        q_values=q_values,
                        objectives=self._objectives,
                        belief=belief_dist,
                    )
                    if resolution:
                        q_values = resolution.get("adjusted_q", q_values)
                        conflicts = resolution.get("conflicts", [])
                except Exception as exc:  # pragma: no cover - defensive integration guard
                    logger.warning("Multi-objective resolution failed: %s", exc)

            prohibited = set(self._roe_constraints.get("prohibited_actions", []))
            roe_mode = str(self._roe_constraints.get("roe_level", "weapons_tight")).lower()

            filtered_q: Dict[str, float] = {}
            for action, value in q_values.items():
                if action in prohibited:
                    continue
                if roe_mode == "weapons_hold" and action == "engage":
                    continue
                filtered_q[action] = value

            if not filtered_q:
                filtered_q = {"hold": q_values.get("hold", 0.0)}

            best_action = max(filtered_q, key=filtered_q.get)
            best_value = filtered_q[best_action]

            concentration = self._belief.concentration()
            dominant_h, dominant_conf = self._belief.max_hypothesis()
            confidence = concentration * min(1.0, abs(best_value) / (abs(best_value) + 0.1))
            confidence = max(0.0, min(1.0, confidence))

            requires_review = confidence < self.config.require_human_review_confidence
            if concentration < (1.0 - self.config.uncertainty_escalation_threshold):
                requires_review = True

            alternatives = sorted(
                [(action, value) for action, value in filtered_q.items() if action != best_action],
                key=lambda item: item[1],
                reverse=True,
            )

            alt_str = ", ".join(f"{action}({value:.3f})" for action, value in alternatives[:3])
            rationale_en = (
                f"Selected '{best_action}' (utility={best_value:.4f}, confidence={confidence:.4f}). "
                f"Belief concentration={concentration:.4f}, dominant hypothesis='{dominant_h}' "
                f"at {dominant_conf:.4f}. Alternatives: [{alt_str}]. "
                f"Memory contexts consulted: {len(memory_context_ids)}."
            )
            rationale_ar = (
                f"تم اختيار '{best_action}' (المنفعة={best_value:.4f}، الثقة={confidence:.4f}). "
                f"تركيز المعتقد={concentration:.4f}، الفرضية السائدة='{dominant_h}' "
                f"عند {dominant_conf:.4f}. البدائل: [{alt_str}]. "
                f"عدد سياقات الذاكرة المُستشارة: {len(memory_context_ids)}."
            )

            decision = CognitiveDecision(
                selected_action=best_action,
                confidence=confidence,
                utility_score=best_value,
                rationale_en=rationale_en,
                rationale_ar=rationale_ar,
                requires_human_review=requires_review,
                alternatives_considered=len(alternatives),
                belief_state_id=state_before.state_id,
                memory_context_ids=memory_context_ids,
                supporting_evidence=[
                    f"obs_{index}" for index in range(cycle.observations_processed)
                ],
            )

            state_after = self._snapshot().model_copy(
                update={
                    "active_objectives": list(self._objectives.keys()),
                    "conflicting_objectives": conflicts,
                    "memory_hits": len(memory_context_ids),
                }
            )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            cycle.state_after = state_after
            cycle.decision = decision
            cycle.elapsed_ms = elapsed_ms

            if elapsed_ms > self.config.max_think_time_ms:
                self._mode = CognitiveMode.DEGRADED

            self._cycle_history.append(cycle)
            if len(self._cycle_history) > self.config.max_cycle_history:
                self._cycle_history = self._cycle_history[-self.config.max_cycle_history :]

        return cycle

    def get_belief(self) -> Dict[str, float]:
        """Return current belief distribution."""
        return self._belief.distribution()

    def get_entropy(self) -> float:
        """Return current belief entropy."""
        return self._belief.entropy()

    def get_concentration(self) -> float:
        """Return belief concentration where 1 means highly certain."""
        return self._belief.concentration()

    def get_history(self, last_n: int = 10) -> List[ThinkCycle]:
        """Return last N cognitive cycles from the in-memory audit history."""
        with self._lock:
            return list(self._cycle_history[-max(0, last_n) :])

    def _snapshot(self) -> CognitiveState:
        """Build an immutable snapshot of current cognitive state."""
        dominant_h, dominant_conf = self._belief.max_hypothesis()
        return CognitiveState(
            mode=self._mode,
            world_entropy=self._belief.entropy(),
            belief_concentration=self._belief.concentration(),
            dominant_hypothesis=dominant_h,
            dominant_confidence=dominant_conf,
        )
