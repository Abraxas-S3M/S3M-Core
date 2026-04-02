"""Belief-state tracking for uncertain tactical contacts.

This module maintains per-track hypothesis clouds so autonomy decisions can
reason over uncertainty instead of relying on brittle deterministic rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import threading
from typing import Any, Dict, List, Optional


@dataclass
class TrackHypothesis:
    """Represents one tactical hypothesis with probabilistic weight."""

    hostile: bool
    intent: str
    weight: float


@dataclass
class TrackBelief:
    """Container for one track's hypothesis cloud and metadata."""

    track_id: str
    hypotheses: List[TrackHypothesis] = field(default_factory=list)
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "TrackBelief":
        total = sum(max(0.0, h.weight) for h in self.hypotheses)
        if total <= 0.0:
            if not self.hypotheses:
                self.hypotheses = [
                    TrackHypothesis(hostile=True, intent="unknown", weight=0.5),
                    TrackHypothesis(hostile=False, intent="unknown", weight=0.5),
                ]
                return self
            uniform = 1.0 / float(len(self.hypotheses))
            for h in self.hypotheses:
                h.weight = uniform
            return self
        for h in self.hypotheses:
            h.weight = max(0.0, h.weight) / total
        return self


class BeliefState:
    """Thread-safe tactical belief store with Bayesian updates."""

    def __init__(self) -> None:
        self._tracks: Dict[str, TrackBelief] = {}
        self._lock = threading.RLock()

    def initialize_track(
        self,
        track_id: str,
        hostile_prior: float = 0.5,
        hostile_intent: str = "attack",
        non_hostile_intent: str = "observe",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize track with two primary military hypotheses."""
        if not track_id:
            raise ValueError("track_id is required")
        p_hostile = max(0.0, min(1.0, float(hostile_prior)))
        with self._lock:
            self._tracks[track_id] = TrackBelief(
                track_id=track_id,
                hypotheses=[
                    TrackHypothesis(hostile=True, intent=hostile_intent, weight=p_hostile),
                    TrackHypothesis(hostile=False, intent=non_hostile_intent, weight=1.0 - p_hostile),
                ],
                metadata=dict(metadata or {}),
            ).normalized()

    def bayesian_update(
        self,
        track_id: str,
        likelihood_hostile: float,
        likelihood_non_hostile: float,
        evidence_confidence: float = 1.0,
        intent_hint: Optional[str] = None,
    ) -> Dict[str, float]:
        """Apply Bayesian evidence update to track's hostile posterior."""
        if not track_id:
            raise ValueError("track_id is required")
        lh = max(1e-9, float(likelihood_hostile))
        ln = max(1e-9, float(likelihood_non_hostile))
        confidence = max(0.0, min(1.0, float(evidence_confidence)))

        with self._lock:
            if track_id not in self._tracks:
                self.initialize_track(track_id=track_id)
            belief = self._tracks[track_id]

            hostile_h = next((h for h in belief.hypotheses if h.hostile), None)
            non_hostile_h = next((h for h in belief.hypotheses if not h.hostile), None)
            if hostile_h is None or non_hostile_h is None:
                self.initialize_track(track_id=track_id)
                belief = self._tracks[track_id]
                hostile_h = next(h for h in belief.hypotheses if h.hostile)
                non_hostile_h = next(h for h in belief.hypotheses if not h.hostile)

            prior_h = max(1e-9, hostile_h.weight)
            prior_n = max(1e-9, non_hostile_h.weight)
            evidence_h = prior_h * lh
            evidence_n = prior_n * ln
            posterior_h = evidence_h / max(evidence_h + evidence_n, 1e-9)

            blended_h = ((1.0 - confidence) * prior_h) + (confidence * posterior_h)
            hostile_h.weight = blended_h
            non_hostile_h.weight = 1.0 - blended_h
            if intent_hint:
                hostile_h.intent = str(intent_hint)
            belief.last_update = datetime.now(timezone.utc)
            belief.normalized()
            return {
                "hostile_probability": hostile_h.weight,
                "non_hostile_probability": non_hostile_h.weight,
            }

    def get_track_probability(self, track_id: str) -> float:
        """Return hostile probability for one track."""
        with self._lock:
            belief = self._tracks.get(track_id)
            if belief is None:
                return 0.5
            for h in belief.hypotheses:
                if h.hostile:
                    return float(h.weight)
            return 0.5

    def get_hostile_tracks(self, threshold: float = 0.7) -> List[str]:
        """Return contacts assessed as hostile for tactical triage."""
        th = max(0.0, min(1.0, float(threshold)))
        with self._lock:
            return [tid for tid in self._tracks if self.get_track_probability(tid) >= th]

    def get_uncertain_tracks(self, lower: float = 0.4, upper: float = 0.6) -> List[str]:
        """Return contacts in ambiguity band requiring cautious handling."""
        lo = max(0.0, min(1.0, float(lower)))
        hi = max(0.0, min(1.0, float(upper)))
        if lo > hi:
            lo, hi = hi, lo
        with self._lock:
            out: List[str] = []
            for tid in self._tracks:
                p = self.get_track_probability(tid)
                if lo <= p <= hi:
                    out.append(tid)
            return out

    def track_entropy(self, track_id: str) -> float:
        """Compute Shannon entropy of one track's hostile belief."""
        p = max(1e-9, min(1.0 - 1e-9, self.get_track_probability(track_id)))
        return float(-p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p))

    def total_entropy(self) -> float:
        """Aggregate uncertainty across all active tracks."""
        with self._lock:
            if not self._tracks:
                return 0.0
            return float(sum(self.track_entropy(tid) for tid in self._tracks))

    def snapshot(self) -> Dict[str, Any]:
        """Return immutable tactical snapshot for read-only consumers."""
        with self._lock:
            payload: Dict[str, Any] = {}
            for tid, belief in self._tracks.items():
                payload[tid] = {
                    "hostile_probability": self.get_track_probability(tid),
                    "entropy": self.track_entropy(tid),
                    "last_update": belief.last_update.isoformat(),
                    "metadata": dict(belief.metadata),
                }
            return payload
