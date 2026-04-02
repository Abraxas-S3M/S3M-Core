"""Data models for short-horizon tactical prediction.

These models are lightweight, deterministic, and edge-safe for offline use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ThreatPosture(str, Enum):
    """Coarse posture trend for tactical forecasts."""

    ESCALATING = "escalating"
    STABLE = "stable"
    DEESCALATING = "deescalating"
    UNKNOWN = "unknown"


@dataclass
class HistoricalObservation:
    """Single historical point for an entity trajectory."""

    timestamp_s: float = 0.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    threat_level: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_s": round(self.timestamp_s, 3),
            "position": [round(v, 3) for v in self.position],
            "speed_mps": round(self.speed_mps, 3),
            "heading_deg": round(self.heading_deg, 3),
            "threat_level": self.threat_level,
        }


@dataclass
class EntitySnapshot:
    """Current tactical state of an observed entity."""

    entity_id: str
    entity_type: str = "unknown"
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    threat_level: str = "unknown"
    behavior_tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    volatility: float = 0.0
    history: List[HistoricalObservation] = field(default_factory=list)

    @property
    def history_depth(self) -> int:
        return len(self.history)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "position": [round(v, 3) for v in self.position],
            "speed_mps": round(self.speed_mps, 3),
            "heading_deg": round(self.heading_deg, 3),
            "threat_level": self.threat_level,
            "behavior_tags": list(self.behavior_tags),
            "confidence": round(self.confidence, 4),
            "volatility": round(self.volatility, 4),
            "history_depth": self.history_depth,
        }


@dataclass
class PredictedEntityState:
    """Predicted state at a given forecast horizon."""

    horizon_s: float = 0.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    threat_level: str = "unknown"
    behavior_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon_s": round(self.horizon_s, 3),
            "position": [round(v, 3) for v in self.position],
            "speed_mps": round(self.speed_mps, 3),
            "heading_deg": round(self.heading_deg, 3),
            "threat_level": self.threat_level,
            "behavior_tags": list(self.behavior_tags),
        }


@dataclass
class UncertaintyEstimate:
    """Simple uncertainty decomposition for downstream consumers."""

    aleatoric: float = 0.1
    epistemic: float = 0.1
    interval_low: float = 0.0
    interval_high: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aleatoric": round(self.aleatoric, 4),
            "epistemic": round(self.epistemic, 4),
            "interval": [round(self.interval_low, 4), round(self.interval_high, 4)],
        }


@dataclass
class ExplanationBlock:
    """Human-readable rationale and factor details for tactical review."""

    summary: str = ""
    factors: Dict[str, float] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
            "evidence": list(self.evidence),
        }


@dataclass
class PredictionHypothesis:
    """Single tactical hypothesis for a forecast window."""

    hypothesis_id: str = ""
    label: str = ""
    probability: float = 0.0
    predicted_state: PredictedEntityState = field(default_factory=PredictedEntityState)
    uncertainty: UncertaintyEstimate = field(default_factory=UncertaintyEstimate)
    explanation: ExplanationBlock = field(default_factory=ExplanationBlock)
    # Chunk 4: calibration and pattern data
    raw_probability: float = 0.0  # pre-calibration probability
    calibrated_confidence: Optional[Dict[str, Any]] = None  # from ConfidenceCalibrator
    matched_motif: Optional[str] = None  # name of best matching motif

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            self.hypothesis_id = f"hyp-{uuid.uuid4().hex[:10]}"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "hypothesis_id": self.hypothesis_id,
            "label": self.label,
            "probability": round(self.probability, 4),
            "predicted_state": self.predicted_state.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "explanation": self.explanation.to_dict(),
        }
        if self.raw_probability > 0:
            d["raw_probability"] = round(self.raw_probability, 4)
        if self.calibrated_confidence is not None:
            d["calibrated_confidence"] = self.calibrated_confidence
        if self.matched_motif:
            d["matched_motif"] = self.matched_motif
        return d


@dataclass
class ForecastWindow:
    """Forecast hypotheses for a specific horizon."""

    horizon_s: float
    hypotheses: List[PredictionHypothesis] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon_s": round(self.horizon_s, 3),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
        }


@dataclass
class ForecastBundle:
    """Top-level forecast output for one entity."""

    entity_id: str = ""
    windows: List[ForecastWindow] = field(default_factory=list)

    # Summary
    overall_trend: ThreatPosture = ThreatPosture.UNKNOWN
    volatility_score: float = 0.0
    forecast_confidence: float = 0.5
    # Chunk 4: pattern and calibration metadata
    matched_motif_name: Optional[str] = None
    motif_match_score: float = 0.0
    calibration_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "windows": [w.to_dict() for w in self.windows],
            "overall_trend": self.overall_trend.value,
            "volatility_score": round(self.volatility_score, 4),
            "forecast_confidence": round(self.forecast_confidence, 4),
            "matched_motif": self.matched_motif_name,
            "motif_match_score": round(self.motif_match_score, 3),
            "calibration_applied": self.calibration_applied,
        }
