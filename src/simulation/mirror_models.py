"""Typed models for the S3M Live Simulation Mirror.

The mirror runs predicted state beside observed state and compares them
to measure forecast quality, detect drift, and produce feedback for
continuous calibration.

Data flow:
  Predictor -> PredictedStateFrame
  Fusion    -> ObservedStateFrame
                  ↓
  MirrorFrame (one per entity per timestep)
                  ↓
  MirrorComparison (position error, classification drift, confidence miss)
                  ↓
  DriftSignal (when predictions diverge significantly)
                  ↓
  ValidationMetric (accumulated precision, recall, calibration error)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =====================================================================
# Enums
# =====================================================================

class DriftSeverity(Enum):
    """How severe the prediction drift is."""

    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class ComparisonOutcome(Enum):
    """Outcome classification of a single prediction comparison."""

    ACCURATE = "accurate"  # prediction matched observation
    PARTIAL_MATCH = "partial_match"  # some dimensions matched
    INACCURATE = "inaccurate"  # prediction was wrong
    ENTITY_MISSING = "entity_missing"  # predicted entity not observed
    FALSE_PERSISTENCE = (
        "false_persistence"  # predicted entity persists but actually gone
    )
    UNEXPECTED_ENTITY = "unexpected_entity"  # observed entity not predicted


# =====================================================================
# State frames
# =====================================================================

@dataclass
class PredictedStateFrame:
    """The predicted state of one entity at a future time, captured when
    the prediction was made.
    """

    frame_id: str = ""
    entity_id: str = ""
    prediction_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    target_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_s: float = 0.0

    # Predicted kinematics
    predicted_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    predicted_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    predicted_heading_deg: float = 0.0
    predicted_speed_mps: float = 0.0

    # Predicted assessment
    predicted_threat_level: str = "unknown"
    predicted_label: str = ""  # hypothesis label (continue_course, stop, etc.)
    predicted_confidence: float = 0.0
    hypothesis_probability: float = 0.0

    # Source
    bundle_id: str = ""
    hypothesis_id: str = ""

    def __post_init__(self) -> None:
        if not self.frame_id:
            self.frame_id = f"pf-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "entity_id": self.entity_id,
            "prediction_timestamp": self.prediction_timestamp.isoformat(),
            "target_timestamp": self.target_timestamp.isoformat(),
            "horizon_s": self.horizon_s,
            "predicted_position": list(self.predicted_position),
            "predicted_heading_deg": round(self.predicted_heading_deg, 1),
            "predicted_speed_mps": round(self.predicted_speed_mps, 2),
            "predicted_threat_level": self.predicted_threat_level,
            "predicted_label": self.predicted_label,
            "predicted_confidence": round(self.predicted_confidence, 4),
        }


@dataclass
class ObservedStateFrame:
    """What was actually observed at the target time."""

    frame_id: str = ""
    entity_id: str = ""
    observation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Observed kinematics
    observed_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    observed_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    observed_heading_deg: float = 0.0
    observed_speed_mps: float = 0.0

    # Observed assessment
    observed_threat_level: str = "unknown"
    observed_classification: str = ""
    observed_confidence: float = 0.5

    # Was the entity actually present?
    entity_present: bool = True

    def __post_init__(self) -> None:
        if not self.frame_id:
            self.frame_id = f"of-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "entity_id": self.entity_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "observed_position": list(self.observed_position),
            "observed_heading_deg": round(self.observed_heading_deg, 1),
            "observed_speed_mps": round(self.observed_speed_mps, 2),
            "observed_threat_level": self.observed_threat_level,
            "entity_present": self.entity_present,
        }


# =====================================================================
# Mirror frame (predicted + observed paired)
# =====================================================================

@dataclass
class MirrorFrame:
    """A paired predicted-vs-observed snapshot for one entity at one time."""

    mirror_id: str = ""
    entity_id: str = ""
    horizon_s: float = 0.0
    predicted: Optional[PredictedStateFrame] = None
    observed: Optional[ObservedStateFrame] = None
    comparison: Optional["MirrorComparison"] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.mirror_id:
            self.mirror_id = f"mf-{uuid.uuid4().hex[:8]}"

    @property
    def is_complete(self) -> bool:
        return self.predicted is not None and self.observed is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mirror_id": self.mirror_id,
            "entity_id": self.entity_id,
            "horizon_s": self.horizon_s,
            "is_complete": self.is_complete,
            "predicted": self.predicted.to_dict() if self.predicted else None,
            "observed": self.observed.to_dict() if self.observed else None,
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


# =====================================================================
# Mirror comparison
# =====================================================================

@dataclass
class MirrorComparison:
    """Quantified comparison between predicted and observed state."""

    comparison_id: str = ""
    entity_id: str = ""
    horizon_s: float = 0.0
    outcome: ComparisonOutcome = ComparisonOutcome.INACCURATE

    # Error metrics
    position_error_m: float = 0.0
    heading_error_deg: float = 0.0
    speed_error_mps: float = 0.0
    threat_level_match: bool = False
    label_match: bool = False

    # Confidence assessment
    predicted_confidence: float = 0.0
    actual_outcome_probability: float = 0.0  # 1.0 if prediction was right
    calibration_error: float = 0.0  # |predicted_conf - actual_outcome|

    # Additional
    entity_was_present: bool = True
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.comparison_id:
            self.comparison_id = f"cmp-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "entity_id": self.entity_id,
            "horizon_s": self.horizon_s,
            "outcome": self.outcome.value,
            "position_error_m": round(self.position_error_m, 2),
            "heading_error_deg": round(self.heading_error_deg, 1),
            "speed_error_mps": round(self.speed_error_mps, 2),
            "threat_level_match": self.threat_level_match,
            "label_match": self.label_match,
            "calibration_error": round(self.calibration_error, 4),
            "notes": list(self.notes),
        }


# =====================================================================
# Drift signal
# =====================================================================

@dataclass
class DriftSignal:
    """Alert generated when predictions consistently diverge from observations."""

    signal_id: str = ""
    entity_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: DriftSeverity = DriftSeverity.MINOR
    drift_type: str = ""  # "position", "classification", "confidence", "presence"
    metric_value: float = 0.0  # the divergence metric
    threshold: float = 0.0  # what threshold was exceeded
    window_comparisons: int = 0  # how many comparisons contributed
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = f"drift-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "drift_type": self.drift_type,
            "metric_value": round(self.metric_value, 4),
            "threshold": round(self.threshold, 4),
            "window_comparisons": self.window_comparisons,
            "explanation": self.explanation,
        }


# =====================================================================
# Validation metric (accumulated)
# =====================================================================

@dataclass
class ValidationMetric:
    """Accumulated validation statistics for the prediction engine."""

    metric_id: str = ""
    window_label: str = ""
    total_comparisons: int = 0

    # Precision-like: of things we predicted, how many were right
    correct_label_predictions: int = 0
    label_precision: float = 0.0

    # Recall-like: of things that happened, how many did we predict
    entities_observed: int = 0
    entities_predicted: int = 0
    detection_recall: float = 0.0

    # Position accuracy
    mean_position_error_m: float = 0.0
    max_position_error_m: float = 0.0

    # Calibration
    mean_calibration_error: float = 0.0

    # Drift
    drift_signals_generated: int = 0

    # Timing
    mean_time_to_correction_s: float = 0.0

    def __post_init__(self) -> None:
        if not self.metric_id:
            self.metric_id = f"vm-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "window_label": self.window_label,
            "total_comparisons": self.total_comparisons,
            "label_precision": round(self.label_precision, 4),
            "detection_recall": round(self.detection_recall, 4),
            "mean_position_error_m": round(self.mean_position_error_m, 2),
            "max_position_error_m": round(self.max_position_error_m, 2),
            "mean_calibration_error": round(self.mean_calibration_error, 4),
            "drift_signals_generated": self.drift_signals_generated,
        }


# =====================================================================
# Feedback output (machine-readable for tuning)
# =====================================================================

@dataclass
class MirrorFeedback:
    """Machine-readable feedback for tuning prediction parameters."""

    feedback_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entity_id: str = ""
    horizon_s: float = 0.0
    predicted_label: str = ""
    actual_outcome: str = ""
    position_error_m: float = 0.0
    calibration_error: float = 0.0
    recommended_adjustments: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.feedback_id:
            self.feedback_id = f"fb-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "entity_id": self.entity_id,
            "horizon_s": self.horizon_s,
            "predicted_label": self.predicted_label,
            "actual_outcome": self.actual_outcome,
            "position_error_m": round(self.position_error_m, 2),
            "calibration_error": round(self.calibration_error, 4),
            "recommended_adjustments": self.recommended_adjustments,
        }
