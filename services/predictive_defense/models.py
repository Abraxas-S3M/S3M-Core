"""Predictive defense data models for interceptor pre-positioning.

Military context:
These schemas carry threat-forecast and launch-order data used to stage
interceptors before hostile tracks reach defended airspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Optional, Tuple

Position3D = Tuple[float, float, float]


def _validate_position(name: str, value: Position3D) -> Position3D:
    if len(value) != 3:
        raise ValueError(f"{name} must be a 3D position tuple")
    x, y, z = float(value[0]), float(value[1]), float(value[2])
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise ValueError(f"{name} must contain finite coordinates")
    return (x, y, z)


class SwarmIntent(str, Enum):
    """High-level hostile swarm intent estimate from tactical intelligence."""

    UNKNOWN = "unknown"
    RECON = "recon"
    PROBE = "probe"
    STRIKE = "strike"
    SATURATION = "saturation"


@dataclass
class ThreatTrajectoryPrediction:
    """Projected threat trajectory used for early interceptor staging."""

    track_id: str
    current_position: Position3D
    current_heading_deg: float
    time_to_asset_s: float
    prediction_confidence: float = 0.5
    predicted_30s: Optional[Position3D] = None
    predicted_60s: Optional[Position3D] = None
    genome_match: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("track_id must be non-empty")
        self.current_position = _validate_position("current_position", self.current_position)
        self.current_heading_deg = float(self.current_heading_deg) % 360.0
        self.time_to_asset_s = float(self.time_to_asset_s)
        self.prediction_confidence = float(self.prediction_confidence)
        if not math.isfinite(self.time_to_asset_s) or self.time_to_asset_s < 0.0:
            raise ValueError("time_to_asset_s must be a finite non-negative value")
        if not math.isfinite(self.prediction_confidence) or not 0.0 <= self.prediction_confidence <= 1.0:
            raise ValueError("prediction_confidence must be in [0.0, 1.0]")
        if self.predicted_30s is not None:
            self.predicted_30s = _validate_position("predicted_30s", self.predicted_30s)
        if self.predicted_60s is not None:
            self.predicted_60s = _validate_position("predicted_60s", self.predicted_60s)


@dataclass
class InterceptWindow:
    """Feasible time window and geometry quality for a threat intercept."""

    window_start_s: float
    window_end_s: float
    optimal_launch_s: float
    intercept_position: Position3D
    intercept_altitude_m: float
    closing_geometry_score: float

    def __post_init__(self) -> None:
        self.window_start_s = float(self.window_start_s)
        self.window_end_s = float(self.window_end_s)
        self.optimal_launch_s = float(self.optimal_launch_s)
        self.intercept_position = _validate_position("intercept_position", self.intercept_position)
        self.intercept_altitude_m = float(self.intercept_altitude_m)
        self.closing_geometry_score = float(self.closing_geometry_score)
        if not math.isfinite(self.window_start_s) or self.window_start_s < 0.0:
            raise ValueError("window_start_s must be a finite non-negative value")
        if not math.isfinite(self.window_end_s) or self.window_end_s < self.window_start_s:
            raise ValueError("window_end_s must be finite and >= window_start_s")
        if not math.isfinite(self.optimal_launch_s) or self.optimal_launch_s < 0.0:
            raise ValueError("optimal_launch_s must be a finite non-negative value")
        if not math.isfinite(self.intercept_altitude_m):
            raise ValueError("intercept_altitude_m must be finite")
        if not math.isfinite(self.closing_geometry_score) or not 0.0 <= self.closing_geometry_score <= 1.0:
            raise ValueError("closing_geometry_score must be in [0.0, 1.0]")


@dataclass
class PrePositionCommand:
    """Launch and stationing command generated for an interceptor sortie."""

    interceptor_id: str
    target_track_id: str
    launch_now: bool
    intercept_position: Position3D
    loiter_altitude_m: float
    launch_time_offset_s: float
    time_to_station_s: float
    engagement_window_s: float
    reasoning: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id must be non-empty")
        if not self.target_track_id:
            raise ValueError("target_track_id must be non-empty")
        self.intercept_position = _validate_position("intercept_position", self.intercept_position)
        self.loiter_altitude_m = float(self.loiter_altitude_m)
        self.launch_time_offset_s = float(self.launch_time_offset_s)
        self.time_to_station_s = float(self.time_to_station_s)
        self.engagement_window_s = float(self.engagement_window_s)
        self.confidence = float(self.confidence)
        if not all(math.isfinite(v) for v in (
            self.loiter_altitude_m,
            self.launch_time_offset_s,
            self.time_to_station_s,
            self.engagement_window_s,
            self.confidence,
        )):
            raise ValueError("command numeric fields must be finite")
        if self.launch_time_offset_s < 0.0 or self.time_to_station_s < 0.0 or self.engagement_window_s < 0.0:
            raise ValueError("timing fields must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0.0, 1.0]")


@dataclass
class SwarmPrediction:
    """Aggregated swarm assessment used to shape tactical launch rationale."""

    track_count: int
    intent: SwarmIntent = SwarmIntent.UNKNOWN
    confidence: float = 0.5

    def __post_init__(self) -> None:
        self.track_count = int(self.track_count)
        self.confidence = float(self.confidence)
        if self.track_count < 1:
            raise ValueError("track_count must be >= 1")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0.0, 1.0]")
