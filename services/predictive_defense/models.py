"""Predictive defense data models for trajectory-to-action orchestration.

Military context:
These structures carry short-horizon threat forecasts into actionable
pre-position and cueing decisions for layered air-defense operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4


def _utc_epoch_s() -> float:
    return datetime.now(timezone.utc).timestamp()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _validate_vec3(value: Tuple[float, float, float], *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3D tuple")
    return (float(value[0]), float(value[1]), float(value[2]))


@dataclass
class InterceptWindow:
    """Time window in which an interceptor should achieve terminal geometry."""

    threat_id: str
    start_time_s: float
    end_time_s: float
    preferred_time_s: float
    intercept_point_m: Tuple[float, float, float]
    confidence: float = 0.5
    window_id: str = field(default_factory=lambda: f"iw-{uuid4().hex[:10]}")

    def __post_init__(self) -> None:
        if self.end_time_s < self.start_time_s:
            raise ValueError("end_time_s must be >= start_time_s")
        self.intercept_point_m = _validate_vec3(self.intercept_point_m, field_name="intercept_point_m")
        self.confidence = _clamp01(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "threat_id": self.threat_id,
            "start_time_s": round(self.start_time_s, 3),
            "end_time_s": round(self.end_time_s, 3),
            "preferred_time_s": round(self.preferred_time_s, 3),
            "intercept_point_m": [round(v, 3) for v in self.intercept_point_m],
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ThreatTrajectoryPrediction:
    """Genome-aware short-horizon trajectory forecast for one track."""

    track_id: str
    name_en: str = "Threat trajectory prediction"
    name_ar: str = "توقع مسار التهديد"
    matched_genome_id: str = ""
    matched_genome_name: str = ""
    matched_genome_confidence: float = 0.0
    forecast_confidence: float = 0.0
    selected_hypothesis: str = ""
    predicted_positions_m: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)
    predicted_speeds_mps: Dict[int, float] = field(default_factory=dict)
    behavior_context: Dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    explanation: List[str] = field(default_factory=list)
    updated_at_s: float = field(default_factory=_utc_epoch_s)

    def __post_init__(self) -> None:
        self.matched_genome_confidence = _clamp01(self.matched_genome_confidence)
        self.forecast_confidence = _clamp01(self.forecast_confidence)
        self.risk_score = _clamp01(self.risk_score)
        normalized: Dict[int, Tuple[float, float, float]] = {}
        for horizon_s, point in self.predicted_positions_m.items():
            normalized[int(horizon_s)] = _validate_vec3(tuple(point), field_name=f"predicted_positions_m[{horizon_s}]")
        self.predicted_positions_m = normalized

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "matched_genome_id": self.matched_genome_id,
            "matched_genome_name": self.matched_genome_name,
            "matched_genome_confidence": round(self.matched_genome_confidence, 4),
            "forecast_confidence": round(self.forecast_confidence, 4),
            "selected_hypothesis": self.selected_hypothesis,
            "predicted_positions_m": {
                str(h): [round(v, 3) for v in p] for h, p in sorted(self.predicted_positions_m.items())
            },
            "predicted_speeds_mps": {
                str(h): round(float(v), 3) for h, v in sorted(self.predicted_speeds_mps.items())
            },
            "behavior_context": dict(self.behavior_context),
            "risk_score": round(self.risk_score, 4),
            "explanation": list(self.explanation),
            "updated_at_s": round(self.updated_at_s, 3),
        }


@dataclass
class SwarmPrediction:
    """Predicted swarm-level behavior including convergence and intent."""

    swarm_id: str
    member_track_ids: List[str]
    convergence_point_m: Tuple[float, float, float]
    eta_to_asset_s: float
    defended_asset_name_en: str
    defended_asset_name_ar: str
    intent_classification: str
    intent_confidence: float = 0.5
    threat_count: int = 0
    dispersion_m: float = 0.0
    updated_at_s: float = field(default_factory=_utc_epoch_s)

    def __post_init__(self) -> None:
        self.convergence_point_m = _validate_vec3(self.convergence_point_m, field_name="convergence_point_m")
        self.eta_to_asset_s = max(0.0, float(self.eta_to_asset_s))
        self.intent_confidence = _clamp01(self.intent_confidence)
        self.threat_count = int(self.threat_count or len(self.member_track_ids))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "member_track_ids": list(self.member_track_ids),
            "convergence_point_m": [round(v, 3) for v in self.convergence_point_m],
            "eta_to_asset_s": round(self.eta_to_asset_s, 3),
            "defended_asset_name_en": self.defended_asset_name_en,
            "defended_asset_name_ar": self.defended_asset_name_ar,
            "intent_classification": self.intent_classification,
            "intent_confidence": round(self.intent_confidence, 4),
            "threat_count": self.threat_count,
            "dispersion_m": round(float(self.dispersion_m), 3),
            "updated_at_s": round(self.updated_at_s, 3),
        }


@dataclass
class PrePositionCommand:
    """Command for interceptor movement before threat enters kill zone."""

    interceptor_id: str
    target_track_id: str
    launch_position_m: Tuple[float, float, float]
    intercept_point_m: Tuple[float, float, float]
    launch_time_s: float
    intercept_time_s: float
    intercept_window: InterceptWindow
    priority: int = 100
    command_mode: str = "predictive_preposition"
    launch_now: bool = False
    name_en: str = "Predictive pre-position command"
    name_ar: str = "أمر تموضع استباقي"
    command_id: str = field(default_factory=lambda: f"ppc-{uuid4().hex[:10]}")

    def __post_init__(self) -> None:
        self.launch_position_m = _validate_vec3(self.launch_position_m, field_name="launch_position_m")
        self.intercept_point_m = _validate_vec3(self.intercept_point_m, field_name="intercept_point_m")
        self.priority = max(1, int(self.priority))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "command_mode": self.command_mode,
            "interceptor_id": self.interceptor_id,
            "target_track_id": self.target_track_id,
            "launch_position_m": [round(v, 3) for v in self.launch_position_m],
            "intercept_point_m": [round(v, 3) for v in self.intercept_point_m],
            "launch_time_s": round(self.launch_time_s, 3),
            "intercept_time_s": round(self.intercept_time_s, 3),
            "priority": self.priority,
            "launch_now": bool(self.launch_now),
            "intercept_window": self.intercept_window.to_dict(),
        }


@dataclass
class PredictiveAlert:
    """Human-readable warning generated from predictive defense analytics."""

    level: str
    message_en: str
    message_ar: str
    related_track_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5
    recommended_actions_en: List[str] = field(default_factory=list)
    recommended_actions_ar: List[str] = field(default_factory=list)
    name_en: str = "Predictive defense alert"
    name_ar: str = "إنذار الدفاع التنبؤي"
    alert_id: str = field(default_factory=lambda: f"pda-{uuid4().hex[:10]}")

    def __post_init__(self) -> None:
        self.confidence = _clamp01(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "level": self.level,
            "message_en": self.message_en,
            "message_ar": self.message_ar,
            "related_track_ids": list(self.related_track_ids),
            "confidence": round(self.confidence, 4),
            "recommended_actions_en": list(self.recommended_actions_en),
            "recommended_actions_ar": list(self.recommended_actions_ar),
        }


@dataclass
class DefensePosture:
    """Full predictive-defense output state for one processing cycle."""

    posture_level: str
    summary_en: str
    summary_ar: str
    trajectory_predictions: List[ThreatTrajectoryPrediction] = field(default_factory=list)
    swarm_predictions: List[SwarmPrediction] = field(default_factory=list)
    preposition_commands: List[PrePositionCommand] = field(default_factory=list)
    alerts: List[PredictiveAlert] = field(default_factory=list)
    allocator_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    interceptor_actions: List[Dict[str, Any]] = field(default_factory=list)
    name_en: str = "Predictive defense posture"
    name_ar: str = "وضعية الدفاع التنبؤي"
    generated_at_s: float = field(default_factory=_utc_epoch_s)
    posture_id: str = field(default_factory=lambda: f"post-{uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "posture_id": self.posture_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "posture_level": self.posture_level,
            "summary_en": self.summary_en,
            "summary_ar": self.summary_ar,
            "generated_at_s": round(self.generated_at_s, 3),
            "trajectory_predictions": [p.to_dict() for p in self.trajectory_predictions],
            "swarm_predictions": [s.to_dict() for s in self.swarm_predictions],
            "preposition_commands": [c.to_dict() for c in self.preposition_commands],
            "alerts": [a.to_dict() for a in self.alerts],
            "allocator_outcomes": [dict(outcome) for outcome in self.allocator_outcomes],
            "interceptor_actions": [dict(action) for action in self.interceptor_actions],
        }
