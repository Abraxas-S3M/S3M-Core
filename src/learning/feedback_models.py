# File: src/learning/feedback_models.py
"""Typed models for the S3M continuous learning feedback interface.

Feedback signals are structured, versioned, and attributable records
that describe WHAT went wrong in predictions and WHAT should be tuned.
They are NOT autonomous code rewrites — they are machine-readable
recommendations for human review or controlled training pipelines.

Signal types:
  - UNDERCONFIDENCE:    system scored too low, actual outcome was correct
  - OVERCONFIDENCE:     system scored too high, actual outcome was wrong
  - FALSE_MERGE:        threat genome merged entities that were distinct
  - MISSED_CORRELATION: related observations were not linked
  - UNSTABLE_MOTIF:     a pattern match keeps flipping between motifs
  - DOCTRINE_MISCALIBRATION: doctrine threshold doesn't match observed rates
  - POSITION_DRIFT:     kinematic predictions consistently off
  - CLASSIFICATION_DRIFT: threat level predictions consistently wrong

Every signal carries:
  - version: schema version for pipeline compatibility
  - source_metric_id: which validation metric or comparison triggered it
  - attribution: what entity/prediction/comparison produced it
  - severity: how urgent the tuning is
  - recommended_action: structured action descriptor (not code)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# =====================================================================
# Enums
# =====================================================================

FEEDBACK_SCHEMA_VERSION = "1.0.0"


class FeedbackSignalType(Enum):
    """Category of feedback signal."""

    UNDERCONFIDENCE = "underconfidence"
    OVERCONFIDENCE = "overconfidence"
    FALSE_MERGE = "false_merge"
    MISSED_CORRELATION = "missed_correlation"
    UNSTABLE_MOTIF = "unstable_motif"
    DOCTRINE_MISCALIBRATION = "doctrine_miscalibration"
    POSITION_DRIFT = "position_drift"
    CLASSIFICATION_DRIFT = "classification_drift"


class FeedbackSeverity(Enum):
    """Urgency of the tuning recommendation."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackStatus(Enum):
    """Lifecycle status of a feedback signal."""

    PENDING = "pending"  # generated, awaiting review
    ACKNOWLEDGED = "acknowledged"  # human reviewed
    APPLIED = "applied"  # tuning was applied
    REJECTED = "rejected"  # human decided not to act
    EXPIRED = "expired"  # too old to be relevant


# =====================================================================
# Recommended action (structured, not code)
# =====================================================================


@dataclass
class RecommendedAction:
    """A structured tuning recommendation, not executable code."""

    action_type: str = ""  # "adjust_threshold", "reinforce_motif", etc.
    target_component: str = ""  # "confidence_calibrator", "pattern_memory", etc.
    target_parameter: str = ""  # specific parameter name
    current_value: Optional[Any] = None
    recommended_value: Optional[Any] = None
    direction: str = ""  # "increase", "decrease", "replace", "add"
    magnitude: float = 0.0  # suggested change magnitude
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_component": self.target_component,
            "target_parameter": self.target_parameter,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "direction": self.direction,
            "magnitude": round(self.magnitude, 4),
            "rationale": self.rationale,
        }


# =====================================================================
# Feedback signal
# =====================================================================


@dataclass
class FeedbackSignal:
    """A single versioned, attributable feedback signal.

    This is the primary output of the feedback generator. It describes
    a specific prediction quality issue and recommends a tuning action.
    """

    signal_id: str = ""
    schema_version: str = FEEDBACK_SCHEMA_VERSION
    signal_type: FeedbackSignalType = FeedbackSignalType.UNDERCONFIDENCE
    severity: FeedbackSeverity = FeedbackSeverity.MEDIUM
    status: FeedbackStatus = FeedbackStatus.PENDING

    # Timing
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    # Attribution
    entity_id: str = ""
    source_metric_id: str = ""  # which ValidationMetric triggered this
    source_comparison_ids: List[str] = field(default_factory=list)
    source_drift_signal_id: str = ""

    # Evidence
    metric_name: str = ""  # e.g., "mean_calibration_error"
    metric_value: float = 0.0
    baseline_value: float = 0.0  # expected / acceptable value
    deviation: float = 0.0  # how far off

    # Context
    window_label: str = ""
    sample_size: int = 0
    description: str = ""

    # Recommendation
    recommended_actions: List[RecommendedAction] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = f"fbs-{uuid.uuid4().hex[:10]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "schema_version": self.schema_version,
            "signal_type": self.signal_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "generated_at": self.generated_at.isoformat(),
            "entity_id": self.entity_id,
            "source_metric_id": self.source_metric_id,
            "source_comparison_ids": list(self.source_comparison_ids),
            "metric_name": self.metric_name,
            "metric_value": round(self.metric_value, 4),
            "baseline_value": round(self.baseline_value, 4),
            "deviation": round(self.deviation, 4),
            "window_label": self.window_label,
            "sample_size": self.sample_size,
            "description": self.description,
            "recommended_actions": [a.to_dict() for a in self.recommended_actions],
        }


# =====================================================================
# Feedback batch (collection of signals from one analysis pass)
# =====================================================================


@dataclass
class FeedbackBatch:
    """A timestamped batch of feedback signals from one analysis cycle."""

    batch_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = FEEDBACK_SCHEMA_VERSION
    signals: List[FeedbackSignal] = field(default_factory=list)
    source_comparisons_analyzed: int = 0
    source_drift_signals_analyzed: int = 0

    def __post_init__(self) -> None:
        if not self.batch_id:
            self.batch_id = f"batch-{uuid.uuid4().hex[:8]}"

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    def by_type(self, signal_type: FeedbackSignalType) -> List[FeedbackSignal]:
        return [s for s in self.signals if s.signal_type == signal_type]

    def by_severity(self, min_severity: FeedbackSeverity) -> List[FeedbackSignal]:
        order = [
            FeedbackSeverity.INFO,
            FeedbackSeverity.LOW,
            FeedbackSeverity.MEDIUM,
            FeedbackSeverity.HIGH,
            FeedbackSeverity.CRITICAL,
        ]
        min_idx = order.index(min_severity)
        return [s for s in self.signals if order.index(s.severity) >= min_idx]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "signal_count": self.signal_count,
            "source_comparisons_analyzed": self.source_comparisons_analyzed,
            "signals": [s.to_dict() for s in self.signals],
            "summary": {t.value: len(self.by_type(t)) for t in FeedbackSignalType if self.by_type(t)},
        }
