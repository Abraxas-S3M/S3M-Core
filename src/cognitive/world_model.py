"""
S3M Bayesian World Model — Real-Time Causal Belief Tracking
============================================================
Maintains a causal graph of world hypotheses, tracks state transitions,
and provides the cognitive engine with structured world-state estimates.

This does not replace `src.belief_state`; it complements it with causal
propagation and temporal world dynamics useful for tactical inference.
"""

from __future__ import annotations

import math
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class HypothesisType(str, Enum):
    """Classification of world hypotheses for tactical reasoning."""

    THREAT = "threat"
    ENVIRONMENT = "environment"
    INTENT = "intent"
    CAPABILITY = "capability"
    POSITION = "position"


class WorldHypothesis(BaseModel):
    """Single world hypothesis with Bayesian prior/posterior and update metadata."""

    hypothesis_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    label: str
    hypothesis_type: HypothesisType = HypothesisType.ENVIRONMENT
    prior: float = Field(default=0.5, ge=0.0, le=1.0)
    posterior: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = 0
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CausalLink(BaseModel):
    """Directed causal relationship from one hypothesis to another."""

    source_id: str
    target_id: str
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    link_type: str = "influences"


class WorldObservation(BaseModel):
    """Structured world observation used for model updates."""

    observation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    affected_hypotheses: Dict[str, float] = Field(default_factory=dict)
    source_reliability: float = Field(default=0.7, ge=0.0, le=1.0)
    observation_type: str = "sensor"
    raw_data: Optional[Dict[str, Any]] = None


class WorldState(BaseModel):
    """Snapshot of complete world-model state at a moment in time."""

    state_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    hypotheses: Dict[str, WorldHypothesis] = Field(default_factory=dict)
    causal_links: List[CausalLink] = Field(default_factory=list)
    entropy: float = 0.0
    observations_total: int = 0


class BayesianWorldModel:
    """
    Causal Bayesian world model with real-time updates and propagation.

    The model is designed for contested battlefield sensing where direct
    evidence is sparse and causal context is required to estimate latent state.
    """

    LOG_FLOOR = -300.0

    def __init__(self, max_hypotheses: int = 64, propagation_depth: int = 3) -> None:
        """Initialize bounded hypothesis/cause graph state."""
        self._hypotheses: Dict[str, WorldHypothesis] = {}
        self._causal_links: List[CausalLink] = []
        self._log_beliefs: Dict[str, float] = {}
        self._max_hypotheses = max_hypotheses
        self._propagation_depth = propagation_depth
        self._observation_count = 0
        self._lock = threading.RLock()

    def add_hypothesis(self, hypothesis: WorldHypothesis) -> None:
        """Add or replace a hypothesis; prune lower-probability tails when bounded."""
        with self._lock:
            self._hypotheses[hypothesis.hypothesis_id] = hypothesis
            self._log_beliefs[hypothesis.hypothesis_id] = math.log(max(1e-30, hypothesis.prior))

            if len(self._hypotheses) > self._max_hypotheses:
                sorted_hypotheses = sorted(
                    self._log_beliefs, key=self._log_beliefs.get, reverse=True
                )
                keep = set(sorted_hypotheses[: self._max_hypotheses])
                self._hypotheses = {key: value for key, value in self._hypotheses.items() if key in keep}
                self._log_beliefs = {key: value for key, value in self._log_beliefs.items() if key in keep}

    def add_causal_link(self, link: CausalLink) -> None:
        """Add directed causal link if both hypotheses are present."""
        with self._lock:
            if link.source_id in self._hypotheses and link.target_id in self._hypotheses:
                self._causal_links.append(link)

    def observe(self, observation: WorldObservation) -> Dict[str, float]:
        """
        Update world beliefs from an observation and causal propagation.

        Returns updated posterior probabilities for hypotheses touched by either
        direct evidence or causal propagation.
        """
        with self._lock:
            self._observation_count += 1
            updated: Dict[str, float] = {}
            weight = max(0.01, observation.source_reliability)

            for hypothesis_id, likelihood in observation.affected_hypotheses.items():
                if hypothesis_id not in self._log_beliefs:
                    continue
                ll = max(1e-30, min(1.0 - 1e-10, likelihood))
                self._log_beliefs[hypothesis_id] += weight * math.log(ll)
                self._log_beliefs[hypothesis_id] = max(
                    self.LOG_FLOOR, self._log_beliefs[hypothesis_id]
                )
                updated[hypothesis_id] = likelihood

            frontier = set(updated.keys())
            for _ in range(self._propagation_depth):
                next_frontier: set[str] = set()
                for link in self._causal_links:
                    if link.source_id in frontier and link.target_id not in updated:
                        source_posterior = self._to_probability(link.source_id)
                        propagated_ll = 0.5 + link.strength * (source_posterior - 0.5)
                        propagated_ll = max(0.01, min(0.99, propagated_ll))
                        damped_weight = weight * link.strength * 0.5
                        self._log_beliefs[link.target_id] += damped_weight * math.log(propagated_ll)
                        self._log_beliefs[link.target_id] = max(
                            self.LOG_FLOOR, self._log_beliefs[link.target_id]
                        )
                        updated[link.target_id] = propagated_ll
                        next_frontier.add(link.target_id)
                frontier = next_frontier
                if not frontier:
                    break

            for hypothesis_id in updated:
                if hypothesis_id in self._hypotheses:
                    hypothesis = self._hypotheses[hypothesis_id]
                    self._hypotheses[hypothesis_id] = hypothesis.model_copy(
                        update={
                            "posterior": self._to_probability(hypothesis_id),
                            "evidence_count": hypothesis.evidence_count + 1,
                            "last_updated": datetime.now(timezone.utc).isoformat(),
                        }
                    )

            return {hypothesis_id: self._to_probability(hypothesis_id) for hypothesis_id in updated}

    def get_posteriors(self) -> Dict[str, float]:
        """Return posterior probability estimates for all tracked hypotheses."""
        with self._lock:
            return {hypothesis_id: self._to_probability(hypothesis_id) for hypothesis_id in self._hypotheses}

    def get_state(self) -> WorldState:
        """Return a full world state snapshot including entropy and graph links."""
        with self._lock:
            posteriors = self.get_posteriors()
            entropy = (
                -sum(
                    prob * math.log(prob + 1e-30) + (1 - prob) * math.log(1 - prob + 1e-30)
                    for prob in posteriors.values()
                )
                if posteriors
                else 0.0
            )
            return WorldState(
                hypotheses=dict(self._hypotheses),
                causal_links=list(self._causal_links),
                entropy=entropy,
                observations_total=self._observation_count,
            )

    def dominant_hypothesis(self) -> Tuple[Optional[str], float]:
        """Return the most probable hypothesis and its posterior."""
        with self._lock:
            posteriors = self.get_posteriors()
            if not posteriors:
                return None, 0.0
            best = max(posteriors, key=posteriors.get)
            return best, posteriors[best]

    def _to_probability(self, hypothesis_id: str) -> float:
        """Convert bounded log-belief to probability using a stable sigmoid."""
        log_belief = self._log_beliefs.get(hypothesis_id, self.LOG_FLOOR)
        if abs(log_belief) < 500:
            return 1.0 / (1.0 + math.exp(-log_belief))
        return 1.0 if log_belief > 0 else 0.0
