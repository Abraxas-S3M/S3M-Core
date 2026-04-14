"""Data models for predictive swarm-defense analysis.

Military context:
These structures represent inbound threat-track forecasts and the resulting
swarm-level intent estimate that operators use to prioritize defenses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple


class SwarmIntent(str, Enum):
    """Operational intent classes for coordinated hostile air swarms."""

    SATURATION = "saturation"
    PROBING = "probing"
    SEQUENTIAL = "sequential"
    DIVERSIONARY = "diversionary"
    UNKNOWN = "unknown"


@dataclass
class ThreatTrajectoryPrediction:
    """Predicted trajectory snapshot for a single inbound threat track."""

    track_id: str
    current_position: Tuple[float, float, float]
    current_speed_mps: float
    time_to_asset_s: float
    predicted_60s: Optional[Tuple[float, float, float]] = None
    genome_match: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.track_id, str) or not self.track_id.strip():
            raise ValueError("track_id must be a non-empty string")
        self.current_position = _validate_xyz(self.current_position, field_name="current_position")
        self.current_speed_mps = _validate_finite(self.current_speed_mps, field_name="current_speed_mps")
        if self.current_speed_mps < 0.0:
            raise ValueError("current_speed_mps must be non-negative")
        self.time_to_asset_s = _validate_finite(self.time_to_asset_s, field_name="time_to_asset_s")
        if self.predicted_60s is not None:
            self.predicted_60s = _validate_xyz(self.predicted_60s, field_name="predicted_60s")


@dataclass
class SwarmPrediction:
    """Aggregated convergence forecast and intent estimate for a threat swarm."""

    track_ids: List[str]
    track_count: int
    intent: SwarmIntent
    convergence_point: Tuple[float, float, float]
    convergence_spread_m: float
    convergence_time_s: float
    approach_bearing_deg: float
    average_speed_mps: float
    first_arrival_s: float
    last_arrival_s: float
    wave_spacing_s: float
    estimated_pk_defense: float
    effectors_required: int
    genome_match: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.track_count <= 0:
            raise ValueError("track_count must be positive")
        if len(self.track_ids) != self.track_count:
            raise ValueError("track_ids length must match track_count")
        self.convergence_point = _validate_xyz(self.convergence_point, field_name="convergence_point")
        self.convergence_spread_m = _validate_finite(self.convergence_spread_m, field_name="convergence_spread_m")
        self.convergence_time_s = _validate_finite(self.convergence_time_s, field_name="convergence_time_s")
        self.approach_bearing_deg = _validate_finite(self.approach_bearing_deg, field_name="approach_bearing_deg") % 360.0
        self.average_speed_mps = _validate_finite(self.average_speed_mps, field_name="average_speed_mps")
        self.first_arrival_s = _validate_finite(self.first_arrival_s, field_name="first_arrival_s")
        self.last_arrival_s = _validate_finite(self.last_arrival_s, field_name="last_arrival_s")
        self.wave_spacing_s = _validate_finite(self.wave_spacing_s, field_name="wave_spacing_s")
        self.estimated_pk_defense = _validate_finite(self.estimated_pk_defense, field_name="estimated_pk_defense")
        if not 0.0 <= self.estimated_pk_defense <= 1.0:
            raise ValueError("estimated_pk_defense must be in [0.0, 1.0]")
        if self.effectors_required <= 0:
            raise ValueError("effectors_required must be positive")


def _validate_xyz(value: Tuple[float, float, float], field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-tuple")
    x = _validate_finite(value[0], field_name=f"{field_name}[0]")
    y = _validate_finite(value[1], field_name=f"{field_name}[1]")
    z = _validate_finite(value[2], field_name=f"{field_name}[2]")
    return (x, y, z)


def _validate_finite(value: float, field_name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric
