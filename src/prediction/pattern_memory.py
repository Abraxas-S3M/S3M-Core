"""Tactical pattern memory for the S3M prediction engine.

Stores reusable behavioral motifs observed in threat actors and provides:
  - Registration of new patterns with feature signatures
  - Lookup by entity traits (speed, heading variance, threat level, tags)
  - Similarity scoring between live entity state and stored patterns
  - Motif transition prediction (loiter → approach → strike)

Patterns are not hard-coded heuristics — they are structured records that
accumulate from operational history. Each carries observation counts,
confidence, and recency so stale patterns decay naturally.

Usage::

    memory = PatternMemory()
    memory.register_defaults()  # seed with doctrinal motifs
    matches = memory.lookup(entity_snapshot, top_k=3)
    transitions = memory.predict_transitions("loiter", top_k=3)
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


# =====================================================================
# Pattern motif
# =====================================================================


@dataclass
class BehavioralMotif:
    """A reusable tactical behavioral pattern.

    Examples: loiter, probe, approach, disperse, regroup, route_deviation,
    intermittent_signal, strike_run, screening, flanking.

    Each motif defines a feature signature — the set of observable traits
    that characterise the behavior — and a transition table listing which
    motifs typically follow this one.
    """

    motif_id: str = ""
    name: str = ""
    description: str = ""
    category: str = "movement"  # movement, comms, posture, coordination

    # Feature signature: the traits that identify this motif
    # Keys are feature names, values are expected ranges or values
    # e.g., {"speed_range_mps": [0, 3], "heading_variance_deg": [0, 10],
    #        "duration_range_s": [60, 600], "altitude_stable": True}
    signature: Dict[str, Any] = field(default_factory=dict)

    # Applicable entity types / tags (empty = universal)
    applicable_types: Set[str] = field(default_factory=set)
    applicable_tags: Set[str] = field(default_factory=set)

    # Transition table: motif_name → transition probability
    transitions: Dict[str, float] = field(default_factory=dict)

    # Metrics
    observation_count: int = 0
    confidence: float = 0.5
    last_observed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    first_observed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.motif_id:
            self.motif_id = f"motif-{uuid.uuid4().hex[:8]}"

    def record_observation(self, confidence_boost: float = 0.05) -> None:
        self.observation_count += 1
        self.last_observed = datetime.now(timezone.utc)
        self.confidence = min(0.99, self.confidence + confidence_boost)

    @property
    def recency_weight(self) -> float:
        age_h = (datetime.now(timezone.utc) - self.last_observed).total_seconds() / 3600.0
        return math.pow(2.0, -age_h / 168.0)  # 1-week halflife

    def to_dict(self) -> Dict[str, Any]:
        return {
            "motif_id": self.motif_id,
            "name": self.name,
            "category": self.category,
            "observation_count": self.observation_count,
            "confidence": round(self.confidence, 3),
            "recency_weight": round(self.recency_weight, 3),
            "transitions": {k: round(v, 3) for k, v in self.transitions.items()},
            "signature_keys": list(self.signature.keys()),
        }


@dataclass
class MotifMatch:
    """Result of matching an entity against a stored motif."""

    motif: BehavioralMotif
    similarity_score: float  # 0-1
    matched_features: List[str]  # which signature features matched
    mismatched_features: List[str]  # which didn't
    effective_score: float = 0.0  # similarity × confidence × recency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "motif_id": self.motif.motif_id,
            "motif_name": self.motif.name,
            "similarity": round(self.similarity_score, 4),
            "effective_score": round(self.effective_score, 4),
            "matched_features": list(self.matched_features),
            "mismatched_features": list(self.mismatched_features),
        }


@dataclass
class TransitionPrediction:
    """Predicted next motif from a current motif."""

    from_motif: str
    to_motif: str
    probability: float
    supporting_observations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_motif,
            "to": self.to_motif,
            "probability": round(self.probability, 4),
            "observations": self.supporting_observations,
        }


# =====================================================================
# Pattern memory
# =====================================================================


class PatternMemory:
    """Persistent tactical motif store with lookup and transition prediction."""

    def __init__(self) -> None:
        self._motifs: Dict[str, BehavioralMotif] = {}
        self._by_name: Dict[str, str] = {}  # name → motif_id

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, motif: BehavioralMotif) -> str:
        """Register or update a motif. Returns motif_id."""
        self._motifs[motif.motif_id] = motif
        self._by_name[motif.name.lower()] = motif.motif_id
        return motif.motif_id

    def get(self, name_or_id: str) -> Optional[BehavioralMotif]:
        mid = self._by_name.get(name_or_id.lower(), name_or_id)
        return self._motifs.get(mid)

    def all_motifs(self) -> List[BehavioralMotif]:
        return list(self._motifs.values())

    def count(self) -> int:
        return len(self._motifs)

    # ------------------------------------------------------------------
    # Lookup by entity traits
    # ------------------------------------------------------------------

    def lookup(
        self,
        entity_traits: Dict[str, Any],
        entity_type: str = "",
        entity_tags: Optional[Set[str]] = None,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> List[MotifMatch]:
        """Find motifs that match an entity's current observable traits.

        Parameters
        ----------
        entity_traits : dict
            Observable features: speed_mps, heading_variance_deg,
            altitude_stable, signal_intermittent, cluster_size, etc.
        entity_type : str
            E.g., "aircraft", "ground_vehicle".
        entity_tags : set of str
            Behavioral tags from the entity.
        top_k : int
            Maximum matches to return.
        min_score : float
            Minimum effective score to include.

        Returns
        -------
        List of MotifMatch, sorted by effective_score descending.
        """
        tags = {t.lower() for t in (entity_tags or set())}
        results: List[MotifMatch] = []

        for motif in self._motifs.values():
            # Type filter
            if motif.applicable_types and entity_type:
                if entity_type.lower() not in {t.lower() for t in motif.applicable_types}:
                    continue

            # Tag filter (if motif specifies required tags, at least one must match)
            if motif.applicable_tags:
                if not (tags & {t.lower() for t in motif.applicable_tags}):
                    continue

            # Score similarity
            sim, matched, mismatched = self._score_signature(motif.signature, entity_traits)
            effective = sim * motif.confidence * motif.recency_weight

            if effective >= min_score:
                results.append(
                    MotifMatch(
                        motif=motif,
                        similarity_score=sim,
                        matched_features=matched,
                        mismatched_features=mismatched,
                        effective_score=effective,
                    )
                )

        results.sort(key=lambda m: m.effective_score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Transition prediction
    # ------------------------------------------------------------------

    def predict_transitions(
        self,
        current_motif_name: str,
        top_k: int = 5,
    ) -> List[TransitionPrediction]:
        """Predict which motifs are likely to follow the current one.

        Uses the stored transition table of the current motif.
        """
        motif = self.get(current_motif_name)
        if motif is None or not motif.transitions:
            return []

        predictions: List[TransitionPrediction] = []
        for next_name, prob in sorted(motif.transitions.items(), key=lambda x: x[1], reverse=True):
            next_motif = self.get(next_name)
            obs = next_motif.observation_count if next_motif else 0
            predictions.append(
                TransitionPrediction(
                    from_motif=motif.name,
                    to_motif=next_name,
                    probability=prob,
                    supporting_observations=obs,
                )
            )

        return predictions[:top_k]

    # ------------------------------------------------------------------
    # Signature scoring
    # ------------------------------------------------------------------

    def _score_signature(
        self,
        signature: Dict[str, Any],
        traits: Dict[str, Any],
    ) -> Tuple[float, List[str], List[str]]:
        """Score how well entity traits match a motif signature.

        Returns (score_0_to_1, matched_feature_names, mismatched_feature_names).
        """
        if not signature:
            return 0.0, [], []

        matched: List[str] = []
        mismatched: List[str] = []
        total = 0
        score_sum = 0.0

        for key, expected in signature.items():
            observed = traits.get(key)
            if observed is None:
                continue  # feature not present — skip, don't penalise
            total += 1

            s = self._feature_match(expected, observed)
            if s >= 0.5:
                matched.append(key)
            else:
                mismatched.append(key)
            score_sum += s

        if total == 0:
            return 0.0, [], []
        return score_sum / total, matched, mismatched

    @staticmethod
    def _feature_match(expected: Any, observed: Any) -> float:
        """Score a single feature comparison. Returns 0.0-1.0."""
        if isinstance(expected, (list, tuple)) and len(expected) == 2:
            # Range match
            if isinstance(observed, (int, float)):
                low, high = float(expected[0]), float(expected[1])
                if low <= float(observed) <= high:
                    return 1.0
                dist = min(abs(float(observed) - low), abs(float(observed) - high))
                span = max(1.0, high - low)
                return max(0.0, 1.0 - dist / (span * 2))
        elif isinstance(expected, bool):
            return 1.0 if observed == expected else 0.0
        elif isinstance(expected, (int, float)):
            if isinstance(observed, (int, float)):
                diff = abs(float(observed) - float(expected))
                return max(0.0, 1.0 - diff / max(abs(float(expected)), 1.0))
        elif isinstance(expected, str):
            return 1.0 if str(observed).lower() == expected.lower() else 0.0
        return 1.0 if observed == expected else 0.0

    # ------------------------------------------------------------------
    # Default doctrinal motifs
    # ------------------------------------------------------------------

    def register_defaults(self) -> int:
        """Seed the memory with standard tactical motifs. Returns count registered."""
        defaults = [
            BehavioralMotif(
                name="loiter",
                category="movement",
                description="Circling or holding position in a defined area",
                signature={
                    "speed_range_mps": [0, 8],
                    "heading_variance_deg": [30, 360],
                    "altitude_stable": True,
                },
                applicable_types={"aircraft", "vessel"},
                transitions={
                    "approach": 0.35,
                    "disperse": 0.20,
                    "loiter": 0.25,
                    "withdraw": 0.10,
                    "probe": 0.10,
                },
                confidence=0.7,
                observation_count=50,
            ),
            BehavioralMotif(
                name="probe",
                category="movement",
                description="Brief advance toward target followed by withdrawal",
                signature={"speed_range_mps": [5, 20], "duration_range_s": [30, 180], "reversal": True},
                applicable_tags={"hostile", "unknown"},
                transitions={
                    "approach": 0.30,
                    "loiter": 0.25,
                    "probe": 0.15,
                    "disperse": 0.20,
                    "withdraw": 0.10,
                },
                confidence=0.65,
                observation_count=30,
            ),
            BehavioralMotif(
                name="approach",
                category="movement",
                description="Steady advance toward target or area of interest",
                signature={"speed_range_mps": [10, 50], "heading_variance_deg": [0, 15], "closing": True},
                applicable_tags={"hostile", "unknown"},
                transitions={
                    "loiter": 0.20,
                    "strike_run": 0.25,
                    "probe": 0.15,
                    "disperse": 0.15,
                    "approach": 0.25,
                },
                confidence=0.7,
                observation_count=40,
            ),
            BehavioralMotif(
                name="disperse",
                category="coordination",
                description="Group breaks formation and scatters in multiple directions",
                signature={
                    "heading_variance_deg": [60, 360],
                    "cluster_expanding": True,
                    "speed_range_mps": [8, 40],
                },
                transitions={
                    "regroup": 0.35,
                    "withdraw": 0.25,
                    "loiter": 0.20,
                    "approach": 0.10,
                    "disperse": 0.10,
                },
                confidence=0.6,
                observation_count=20,
            ),
            BehavioralMotif(
                name="regroup",
                category="coordination",
                description="Scattered elements converge to a rally point",
                signature={
                    "cluster_contracting": True,
                    "heading_variance_deg": [20, 90],
                    "speed_range_mps": [5, 25],
                },
                transitions={
                    "approach": 0.30,
                    "loiter": 0.30,
                    "disperse": 0.10,
                    "probe": 0.15,
                    "regroup": 0.15,
                },
                confidence=0.6,
                observation_count=15,
            ),
            BehavioralMotif(
                name="intermittent_signal",
                category="comms",
                description="Periodic bursts of electronic emissions with silent intervals",
                signature={
                    "signal_intermittent": True,
                    "burst_interval_range_s": [1, 30],
                    "emission_detected": True,
                },
                applicable_types={"aircraft", "cyber_indicator"},
                transitions={"approach": 0.25, "loiter": 0.30, "intermittent_signal": 0.25, "withdraw": 0.20},
                confidence=0.55,
                observation_count=25,
            ),
            BehavioralMotif(
                name="route_deviation",
                category="movement",
                description="Departure from expected route or patrol pattern",
                signature={"heading_deviation_deg": [20, 180], "off_route": True, "speed_range_mps": [5, 40]},
                transitions={
                    "approach": 0.20,
                    "probe": 0.25,
                    "loiter": 0.20,
                    "route_deviation": 0.15,
                    "withdraw": 0.20,
                },
                confidence=0.5,
                observation_count=20,
            ),
            BehavioralMotif(
                name="withdraw",
                category="movement",
                description="Retreating from area at speed",
                signature={"speed_range_mps": [10, 50], "heading_variance_deg": [0, 20], "moving_away": True},
                transitions={
                    "loiter": 0.20,
                    "disperse": 0.15,
                    "regroup": 0.30,
                    "withdraw": 0.25,
                    "probe": 0.10,
                },
                confidence=0.65,
                observation_count=30,
            ),
            BehavioralMotif(
                name="strike_run",
                category="movement",
                description="High-speed direct approach followed by rapid withdrawal",
                signature={"speed_range_mps": [30, 80], "heading_variance_deg": [0, 10], "high_speed": True},
                applicable_tags={"hostile"},
                transitions={"withdraw": 0.50, "disperse": 0.25, "loiter": 0.10, "approach": 0.15},
                confidence=0.6,
                observation_count=10,
            ),
        ]
        for motif in defaults:
            self.register(motif)
        return len(defaults)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "total_motifs": len(self._motifs),
            "categories": list({m.category for m in self._motifs.values()}),
            "total_observations": sum(m.observation_count for m in self._motifs.values()),
        }
