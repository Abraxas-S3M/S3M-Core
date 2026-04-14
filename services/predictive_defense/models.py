"""Data models for predictive defense orchestration.

Military context:
These structures carry deterministic command-post outputs for doctrinal
pre-positioning, swarm interpretation, and threat-timeline alerting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import List, Optional, Tuple


def _validate_position(position: Tuple[float, float, float], *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(position, tuple) or len(position) != 3:
        raise ValueError(f"{field_name} must be a tuple of three coordinates")
    x, y, z = float(position[0]), float(position[1]), float(position[2])
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError(f"{field_name} values must be finite")
    return (x, y, z)


def _validate_non_negative(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


class DefensePosture(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    PRE_POSITION = "pre_position"
    IMMINENT = "imminent"


class SwarmIntent(str, Enum):
    RECON = "recon"
    PROBE = "probe"
    STRIKE = "strike"
    UNKNOWN = "unknown"


@dataclass
class ThreatTrajectoryPrediction:
    track_id: str
    predicted_position: Tuple[float, float, float]
    time_to_asset_s: float
    distance_to_asset_m: float
    approach_speed_mps: float
    confidence: float = 0.5
    genome_match: Optional[str] = None
    risk_score: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.track_id, str) or not self.track_id.strip():
            raise ValueError("track_id must be a non-empty string")
        self.track_id = self.track_id.strip()
        self.predicted_position = _validate_position(self.predicted_position, field_name="predicted_position")
        self.time_to_asset_s = _validate_non_negative(self.time_to_asset_s, field_name="time_to_asset_s")
        self.distance_to_asset_m = _validate_non_negative(self.distance_to_asset_m, field_name="distance_to_asset_m")
        self.approach_speed_mps = _validate_non_negative(self.approach_speed_mps, field_name="approach_speed_mps")
        self.confidence = float(self.confidence)
        if not isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0.0, 1.0]")
        self.risk_score = _validate_non_negative(self.risk_score, field_name="risk_score")
        if self.genome_match is not None:
            self.genome_match = str(self.genome_match).strip() or None


@dataclass
class SwarmPrediction:
    track_count: int
    centroid_position: Tuple[float, float, float]
    convergence_time_s: float
    intent: SwarmIntent = SwarmIntent.UNKNOWN
    dispersion_m: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.track_count, int) or self.track_count < 0:
            raise ValueError("track_count must be a non-negative integer")
        self.centroid_position = _validate_position(self.centroid_position, field_name="centroid_position")
        self.convergence_time_s = _validate_non_negative(
            self.convergence_time_s,
            field_name="convergence_time_s",
        )
        self.dispersion_m = _validate_non_negative(self.dispersion_m, field_name="dispersion_m")
        if not isinstance(self.intent, SwarmIntent):
            self.intent = SwarmIntent(str(self.intent))


@dataclass
class PrePositionCommand:
    interceptor_id: str
    target_track_id: str
    staging_position: Tuple[float, float, float]
    eta_s: float
    launch_now: bool = False
    rationale: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.interceptor_id, str) or not self.interceptor_id.strip():
            raise ValueError("interceptor_id must be a non-empty string")
        if not isinstance(self.target_track_id, str) or not self.target_track_id.strip():
            raise ValueError("target_track_id must be a non-empty string")
        self.interceptor_id = self.interceptor_id.strip()
        self.target_track_id = self.target_track_id.strip()
        self.staging_position = _validate_position(self.staging_position, field_name="staging_position")
        self.eta_s = _validate_non_negative(self.eta_s, field_name="eta_s")
        self.launch_now = bool(self.launch_now)
        self.rationale = str(self.rationale)


@dataclass
class PredictiveAlert:
    severity: str
    posture: DefensePosture
    title_en: str
    title_ar: str
    description: str = ""
    threat_count: int = 0
    time_to_impact_s: Optional[float] = None
    recommended_actions: List[str] = field(default_factory=list)
    pre_position_commands: List[PrePositionCommand] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        allowed = {"low", "medium", "high", "critical"}
        severity = str(self.severity).strip().lower()
        if severity not in allowed:
            raise ValueError(f"severity must be one of {sorted(allowed)}")
        self.severity = severity
        if not isinstance(self.posture, DefensePosture):
            self.posture = DefensePosture(str(self.posture))
        if not isinstance(self.title_en, str) or not self.title_en.strip():
            raise ValueError("title_en must be a non-empty string")
        if not isinstance(self.title_ar, str) or not self.title_ar.strip():
            raise ValueError("title_ar must be a non-empty string")
        self.title_en = self.title_en.strip()
        self.title_ar = self.title_ar.strip()
        self.description = str(self.description)
        if not isinstance(self.threat_count, int) or self.threat_count < 0:
            raise ValueError("threat_count must be a non-negative integer")
        if self.time_to_impact_s is not None:
            self.time_to_impact_s = _validate_non_negative(self.time_to_impact_s, field_name="time_to_impact_s")
        if any(not isinstance(action, str) for action in self.recommended_actions):
            raise ValueError("recommended_actions must be a list of strings")
        if any(not isinstance(cmd, PrePositionCommand) for cmd in self.pre_position_commands):
            raise ValueError("pre_position_commands must be PrePositionCommand objects")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")
