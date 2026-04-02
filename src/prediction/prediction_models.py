# File: src/prediction/prediction_models.py
"""Typed models for the S3M short-horizon prediction engine.

Data flow:
  EntitySnapshot + PredictionRequest
    -> ShortHorizonPredictor
    -> ForecastBundle
        └─ PredictionWindow[]
            └─ PredictionHypothesis[]
                ├─ PredictedEntityState
                ├─ UncertaintyEstimate
                └─ ExplanationBlock

Every forecast is multi-hypothesis: the system never outputs a single
future.  Each hypothesis carries a probability, a predicted state, an
uncertainty envelope, and a human-readable explanation of why this
future was considered and how confident the engine is.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =====================================================================
# Enums
# =====================================================================


class ThreatPosture(Enum):
    """Predicted behavioral posture."""

    ESCALATING = "escalating"
    STABLE = "stable"
    DE_ESCALATING = "de_escalating"
    MANEUVERING = "maneuvering"
    WITHDRAWING = "withdrawing"
    UNKNOWN = "unknown"


class MovementMode(Enum):
    """Predicted movement behavior."""

    CONTINUE_COURSE = "continue_course"
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STOPPED = "stopped"
    TURNING = "turning"
    REVERSING = "reversing"
    ERRATIC = "erratic"
    UNKNOWN = "unknown"


class CoordinationIndicator(Enum):
    """Indicators of multi-entity coordinated behavior."""

    NONE_DETECTED = "none_detected"
    CONVERGING = "converging"
    FORMATION_CHANGE = "formation_change"
    SYNCHRONIZED_MANEUVER = "synchronized_maneuver"
    SWARM_PATTERN = "swarm_pattern"
    RELAY_PATTERN = "relay_pattern"


# =====================================================================
# Entity snapshot (input)
# =====================================================================


@dataclass
class HistoryPoint:
    """One historical state observation for trend analysis."""

    timestamp: datetime
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    speed_mps: float = 0.0
    threat_level: str = "unknown"
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "position": list(self.position),
            "velocity": list(self.velocity),
            "heading_deg": round(self.heading_deg, 1),
            "speed_mps": round(self.speed_mps, 2),
            "threat_level": self.threat_level,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class EntitySnapshot:
    """Current state of an entity to be forecasted.

    This is the predictor's input.  It captures the entity's latest known
    state plus its recent history for trend analysis.
    """

    entity_id: str = ""
    entity_type: str = "unknown"
    classification: str = ""
    allegiance: str = "unknown"

    # Current kinematic state
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    speed_mps: float = 0.0

    # Current assessment
    threat_level: str = "unknown"
    confidence: float = 0.5
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # State history (most recent first)
    history: List[HistoryPoint] = field(default_factory=list)

    # Optional behavioral tags
    behavior_tags: List[str] = field(default_factory=list)

    # Optional genome reference
    genome_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.entity_id:
            self.entity_id = f"snap-{uuid.uuid4().hex[:8]}"
        self.speed_mps = (
            math.sqrt(
                self.velocity[0] ** 2 + self.velocity[1] ** 2 + self.velocity[2] ** 2
            )
            if self.speed_mps == 0 and any(v != 0 for v in self.velocity)
            else self.speed_mps
        )

    @property
    def is_moving(self) -> bool:
        return self.speed_mps > 0.5

    @property
    def history_depth(self) -> int:
        return len(self.history)

    @property
    def volatility(self) -> float:
        """Quantify how erratically the entity has behaved.

        0.0 = perfectly stable, 1.0 = maximally erratic.
        Computed from heading variance and speed variance in history.
        """
        if len(self.history) < 3:
            return 0.0
        headings = [h.heading_deg for h in self.history[-10:]]
        speeds = [h.speed_mps for h in self.history[-10:]]
        heading_var = _variance(headings)
        speed_var = _variance(speeds)
        # Normalize: heading_var in [0, ~180^2], speed_var in [0, ~50^2]
        h_norm = min(1.0, heading_var / 3600.0)
        s_norm = min(1.0, speed_var / 625.0)
        return min(1.0, (h_norm + s_norm) / 2.0)


# =====================================================================
# Prediction request
# =====================================================================


@dataclass
class PredictionRequest:
    """What to predict, for which windows, with optional context."""

    request_id: str = ""
    entity: Optional[EntitySnapshot] = None
    entities: List[EntitySnapshot] = field(default_factory=list)

    # Time horizons in seconds
    windows_seconds: List[float] = field(default_factory=lambda: [30.0, 120.0, 600.0])

    # Maximum hypotheses per window
    max_hypotheses: int = 5

    # Optional context
    scenario_context: Dict[str, Any] = field(default_factory=dict)
    doctrine_bias: Optional[str] = None  # e.g., "defensive", "aggressive", "neutral"
    operating_mode: Optional[str] = None  # e.g., "patrol", "pursuit", "retreat"

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = f"pred-{uuid.uuid4().hex[:8]}"
        if self.entity and self.entity not in self.entities:
            self.entities.insert(0, self.entity)


# =====================================================================
# Predicted state (output component)
# =====================================================================


@dataclass
class PredictedEntityState:
    """Forecasted state of an entity at a future time."""

    predicted_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    predicted_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    predicted_heading_deg: float = 0.0
    predicted_speed_mps: float = 0.0
    predicted_threat_level: str = "unknown"
    predicted_posture: ThreatPosture = ThreatPosture.UNKNOWN
    movement_mode: MovementMode = MovementMode.UNKNOWN
    coordination_indicators: List[CoordinationIndicator] = field(
        default_factory=lambda: [CoordinationIndicator.NONE_DETECTED]
    )
    predicted_allegiance: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": [round(v, 2) for v in self.predicted_position],
            "velocity": [round(v, 2) for v in self.predicted_velocity],
            "heading_deg": round(self.predicted_heading_deg, 1),
            "speed_mps": round(self.predicted_speed_mps, 2),
            "threat_level": self.predicted_threat_level,
            "posture": self.predicted_posture.value,
            "movement": self.movement_mode.value,
            "coordination": [c.value for c in self.coordination_indicators],
        }


# =====================================================================
# Uncertainty estimate
# =====================================================================


@dataclass
class UncertaintyEstimate:
    """Quantified uncertainty envelope around a predicted state.

    Every dimension of uncertainty is explicit and grows with time horizon.
    """

    spatial_radius_m: float = 0.0  # positional uncertainty radius
    heading_std_deg: float = 0.0  # heading uncertainty (1-sigma)
    speed_std_mps: float = 0.0  # speed uncertainty (1-sigma)
    threat_level_entropy: float = 0.0  # Shannon entropy over threat levels
    classification_entropy: float = 0.0
    temporal_confidence: float = 1.0  # decays with forecast horizon

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spatial_radius_m": round(self.spatial_radius_m, 2),
            "heading_std_deg": round(self.heading_std_deg, 1),
            "speed_std_mps": round(self.speed_std_mps, 2),
            "threat_level_entropy": round(self.threat_level_entropy, 3),
            "temporal_confidence": round(self.temporal_confidence, 3),
        }


# =====================================================================
# Explanation block
# =====================================================================


@dataclass
class ExplanationBlock:
    """Human-readable explanation of why a hypothesis was generated."""

    primary_factors: List[str] = field(default_factory=list)
    supporting_observations: List[str] = field(default_factory=list)
    uncertainty_notes: List[str] = field(default_factory=list)
    methodology: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_factors": list(self.primary_factors),
            "supporting_observations": list(self.supporting_observations),
            "uncertainty_notes": list(self.uncertainty_notes),
            "methodology": self.methodology,
        }


# =====================================================================
# Prediction hypothesis
# =====================================================================


@dataclass
class PredictionHypothesis:
    """One possible future state with probability and explanation.

    The engine generates multiple hypotheses per time window.
    Probabilities across all hypotheses within a window should sum to ~1.0.
    """

    hypothesis_id: str = ""
    label: str = ""  # e.g., "continue_course", "turn_and_evade"
    probability: float = 0.0  # 0-1, sums to ~1 within a window
    predicted_state: PredictedEntityState = field(default_factory=PredictedEntityState)
    uncertainty: UncertaintyEstimate = field(default_factory=UncertaintyEstimate)
    explanation: ExplanationBlock = field(default_factory=ExplanationBlock)

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            self.hypothesis_id = f"hyp-{uuid.uuid4().hex[:6]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "label": self.label,
            "probability": round(self.probability, 4),
            "predicted_state": self.predicted_state.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "explanation": self.explanation.to_dict(),
        }


# =====================================================================
# Prediction window
# =====================================================================


@dataclass
class PredictionWindow:
    """All hypotheses for one time horizon."""

    window_seconds: float = 0.0
    window_label: str = ""  # e.g., "30s", "2min", "10min"
    hypotheses: List[PredictionHypothesis] = field(default_factory=list)
    dominant_hypothesis_id: Optional[str] = None
    aggregate_uncertainty: Optional[UncertaintyEstimate] = None

    def __post_init__(self) -> None:
        if not self.window_label:
            if self.window_seconds < 60:
                self.window_label = f"{int(self.window_seconds)}s"
            else:
                self.window_label = f"{int(self.window_seconds / 60)}min"

    @property
    def dominant(self) -> Optional[PredictionHypothesis]:
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda h: h.probability)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_seconds": self.window_seconds,
            "window_label": self.window_label,
            "hypothesis_count": len(self.hypotheses),
            "dominant_hypothesis": self.dominant_hypothesis_id,
            "aggregate_uncertainty": (
                self.aggregate_uncertainty.to_dict() if self.aggregate_uncertainty else None
            ),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
        }


# =====================================================================
# Forecast bundle (complete output for one entity)
# =====================================================================


@dataclass
class ForecastBundle:
    """Complete prediction output for one entity across all time windows.

    This is the top-level deliverable of the prediction engine.
    """

    bundle_id: str = ""
    request_id: str = ""
    entity_id: str = ""
    entity_classification: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    windows: List[PredictionWindow] = field(default_factory=list)

    # Summary
    overall_trend: ThreatPosture = ThreatPosture.UNKNOWN
    volatility_score: float = 0.0
    forecast_confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.bundle_id:
            self.bundle_id = f"fcst-{uuid.uuid4().hex[:8]}"

    def get_window(self, seconds: float) -> Optional[PredictionWindow]:
        """Find a window by its time horizon."""
        for w in self.windows:
            if abs(w.window_seconds - seconds) < 1.0:
                return w
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "request_id": self.request_id,
            "entity_id": self.entity_id,
            "entity_classification": self.entity_classification,
            "generated_at": self.generated_at.isoformat(),
            "overall_trend": self.overall_trend.value,
            "volatility_score": round(self.volatility_score, 3),
            "forecast_confidence": round(self.forecast_confidence, 3),
            "window_count": len(self.windows),
            "windows": [w.to_dict() for w in self.windows],
        }


# =====================================================================
# Helpers
# =====================================================================


def _variance(values: List[float]) -> float:
    """Population variance."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)
