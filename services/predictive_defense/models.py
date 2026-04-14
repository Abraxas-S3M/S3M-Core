"""Data models for the predictive threat trajectory engine.

Military context:
These models represent predicted threat trajectories, swarm convergence
analysis, and pre-positioning commands — the information products that
give S3M a predictive defense advantage over reactive C2 systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


class DefensePosture(str, Enum):
    """Recommended defensive posture based on prediction confidence."""

    NORMAL = "normal"
    ELEVATED = "elevated"       # Threats predicted but distant
    PRE_POSITION = "pre_position"  # Launch interceptors to predicted positions
    IMMINENT = "imminent"        # Threats entering defense zones within 60s
    ENGAGEMENT = "engagement"    # Active engagement underway


class SwarmIntent(str, Enum):
    """Classified swarm attack intent."""

    SATURATION = "saturation"    # Overwhelming defense with numbers
    PROBING = "probing"          # Testing defenses, may withdraw
    DIVERSIONARY = "diversionary"  # Drawing attention from real attack vector
    SEQUENTIAL = "sequential"    # Waves timed for effector reload gaps
    UNKNOWN = "unknown"


@dataclass
class ThreatTrajectoryPrediction:
    """Predicted trajectory for a single threat track.

    Military context:
    Combines kinematic extrapolation with threat genome behavioral bias.
    A track matched to the Houthi drone genome gets its forecast adjusted
    for known approach vectors, speed profiles, and temporal patterns.
    """

    prediction_id: str = field(default_factory=lambda: f"ttp-{uuid4().hex[:10]}")
    track_id: str = ""
    target_classification: str = "UNKNOWN"
    genome_match: Optional[str] = None
    genome_confidence: float = 0.0

    current_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    current_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    current_speed_mps: float = 0.0
    current_heading_deg: float = 0.0

    # Predicted positions at forecast horizons
    predicted_30s: Optional[Tuple[float, float, float]] = None
    predicted_60s: Optional[Tuple[float, float, float]] = None
    predicted_120s: Optional[Tuple[float, float, float]] = None

    # Range to defended asset at each horizon
    range_to_asset_now_m: float = 0.0
    range_to_asset_30s_m: float = 0.0
    range_to_asset_60s_m: float = 0.0
    range_to_asset_120s_m: float = 0.0

    # Time estimates
    time_to_zone_entry_s: float = 0.0   # When threat enters outermost defense zone
    time_to_asset_s: float = 0.0        # When threat reaches defended asset

    # Confidence
    prediction_confidence: float = 0.0
    genome_bias_applied: bool = False
    behavioral_pattern: str = ""         # e.g., "approach", "loiter", "probe"

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "track_id": self.track_id,
            "classification": self.target_classification,
            "genome_match": self.genome_match,
            "genome_confidence": round(self.genome_confidence, 3),
            "current_position": list(self.current_position),
            "current_speed_mps": round(self.current_speed_mps, 1),
            "current_heading_deg": round(self.current_heading_deg, 1),
            "predicted_30s": list(self.predicted_30s) if self.predicted_30s else None,
            "predicted_60s": list(self.predicted_60s) if self.predicted_60s else None,
            "predicted_120s": list(self.predicted_120s) if self.predicted_120s else None,
            "range_to_asset_now_m": round(self.range_to_asset_now_m, 0),
            "time_to_zone_entry_s": round(self.time_to_zone_entry_s, 1),
            "time_to_asset_s": round(self.time_to_asset_s, 1),
            "confidence": round(self.prediction_confidence, 3),
            "genome_bias": self.genome_bias_applied,
            "behavioral_pattern": self.behavioral_pattern,
        }


@dataclass
class SwarmPrediction:
    """Swarm-level analysis across multiple correlated threat tracks.

    Military context:
    Detects coordinated attack formations, predicts convergence point
    and timing, and classifies attack intent to inform defensive posture.
    """

    swarm_id: str = field(default_factory=lambda: f"swarm-{uuid4().hex[:8]}")
    track_ids: List[str] = field(default_factory=list)
    track_count: int = 0
    intent: SwarmIntent = SwarmIntent.UNKNOWN

    # Convergence analysis
    convergence_point: Optional[Tuple[float, float, float]] = None
    convergence_spread_m: float = 0.0   # Spatial spread at convergence
    convergence_time_s: float = 0.0     # Time until convergence
    approach_bearing_deg: float = 0.0
    average_speed_mps: float = 0.0

    # Timing analysis
    first_arrival_s: float = 0.0        # When first element arrives
    last_arrival_s: float = 0.0         # When last element arrives
    wave_spacing_s: float = 0.0         # Time between successive waves

    # Threat assessment
    estimated_pk_defense: float = 0.0   # Estimated Pk of current defense posture
    effectors_required: int = 0
    genome_match: Optional[str] = None

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "track_count": self.track_count,
            "intent": self.intent.value,
            "convergence_point": list(self.convergence_point) if self.convergence_point else None,
            "convergence_time_s": round(self.convergence_time_s, 1),
            "approach_bearing_deg": round(self.approach_bearing_deg, 1),
            "average_speed_mps": round(self.average_speed_mps, 1),
            "first_arrival_s": round(self.first_arrival_s, 1),
            "last_arrival_s": round(self.last_arrival_s, 1),
            "effectors_required": self.effectors_required,
            "estimated_pk_defense": round(self.estimated_pk_defense, 3),
            "genome_match": self.genome_match,
        }


@dataclass
class PrePositionCommand:
    """Command to pre-position an interceptor drone at a predicted intercept point."""

    command_id: str = field(default_factory=lambda: f"ppc-{uuid4().hex[:8]}")
    interceptor_id: str = ""
    target_track_id: str = ""
    launch_now: bool = False

    # Where to position the interceptor
    intercept_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    loiter_altitude_m: float = 0.0

    # Timing
    launch_time_offset_s: float = 0.0   # Seconds from now to launch
    time_to_station_s: float = 0.0      # Time for interceptor to reach position
    engagement_window_s: float = 0.0    # Available engagement time at position

    # Rationale
    reasoning: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "interceptor_id": self.interceptor_id,
            "target_track_id": self.target_track_id,
            "launch_now": self.launch_now,
            "intercept_position": list(self.intercept_position),
            "launch_offset_s": round(self.launch_time_offset_s, 1),
            "time_to_station_s": round(self.time_to_station_s, 1),
            "engagement_window_s": round(self.engagement_window_s, 1),
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class InterceptWindow:
    """Computed time/space window where an intercept is geometrically possible."""

    window_start_s: float = 0.0
    window_end_s: float = 0.0
    optimal_launch_s: float = 0.0       # Best launch time for max engagement window
    intercept_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    intercept_altitude_m: float = 0.0
    closing_geometry_score: float = 0.0  # 0-1, higher = better intercept geometry


@dataclass
class PredictiveAlert:
    """Alert generated by the predictive defense engine."""

    alert_id: str = field(default_factory=lambda: f"pa-{uuid4().hex[:8]}")
    severity: str = "medium"    # low, medium, high, critical
    posture: DefensePosture = DefensePosture.NORMAL
    title_en: str = ""
    title_ar: str = ""
    description: str = ""
    threat_count: int = 0
    time_to_impact_s: float = 0.0
    recommended_actions: List[str] = field(default_factory=list)
    pre_position_commands: List[PrePositionCommand] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "posture": self.posture.value,
            "title_en": self.title_en,
            "title_ar": self.title_ar,
            "threat_count": self.threat_count,
            "time_to_impact_s": round(self.time_to_impact_s, 1),
            "recommended_actions": self.recommended_actions,
            "pre_position_commands": [c.to_dict() for c in self.pre_position_commands],
        }
