"""Core data models for interceptor guidance loops.

Military context:
These structures represent the fire-control state exchanged between command
guidance and the interceptor during a live engagement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Optional, Tuple


def _validate_vector3(
    value: Tuple[float, float, float],
    *,
    field_name: str,
) -> Tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three coordinates")
    x, y, z = float(value[0]), float(value[1]), float(value[2])
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError(f"{field_name} coordinates must be finite values")
    return (x, y, z)


def _validate_non_negative(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


class GuidanceMode(str, Enum):
    PURE_PURSUIT = "pure_pursuit"
    LEAD_PURSUIT = "lead_pursuit"
    PROPORTIONAL_NAV = "proportional_navigation"


class GuidancePhase(str, Enum):
    PRE_LAUNCH = "pre_launch"
    BOOST = "boost"
    MIDCOURSE = "midcourse"
    TERMINAL = "terminal"
    AUTONOMOUS = "autonomous"
    POST_ENGAGE = "post_engage"


class InterceptorState(str, Enum):
    READY = "ready"
    LAUNCHED = "launched"
    GUIDING = "guiding"
    ENGAGED = "engaged"
    MISS = "miss"
    LOST = "lost"


@dataclass
class HandoffConfig:
    enable_autonomous: bool = True
    min_handoff_range_m: float = 200.0
    max_handoff_range_m: float = 300.0
    terminal_range_m: float = 1_200.0
    hit_radius_m: float = 15.0

    def __post_init__(self) -> None:
        self.min_handoff_range_m = _validate_non_negative(
            self.min_handoff_range_m,
            field_name="min_handoff_range_m",
        )
        self.max_handoff_range_m = _validate_non_negative(
            self.max_handoff_range_m,
            field_name="max_handoff_range_m",
        )
        self.terminal_range_m = _validate_non_negative(
            self.terminal_range_m,
            field_name="terminal_range_m",
        )
        self.hit_radius_m = _validate_non_negative(self.hit_radius_m, field_name="hit_radius_m")
        if self.max_handoff_range_m < self.min_handoff_range_m:
            raise ValueError("max_handoff_range_m must be >= min_handoff_range_m")
        if self.terminal_range_m < self.max_handoff_range_m:
            raise ValueError("terminal_range_m must be >= max_handoff_range_m")


@dataclass
class InterceptorConfig:
    interceptor_id: str
    guidance_update_hz: float = 10.0
    nav_constant: float = 3.0
    max_lateral_accel_mps2: float = 40.0
    max_vertical_accel_mps2: float = 30.0
    handoff: HandoffConfig = field(default_factory=HandoffConfig)

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        self.guidance_update_hz = _validate_non_negative(
            self.guidance_update_hz,
            field_name="guidance_update_hz",
        )
        if self.guidance_update_hz <= 0.0:
            raise ValueError("guidance_update_hz must be > 0.0")
        self.nav_constant = _validate_non_negative(self.nav_constant, field_name="nav_constant")
        self.max_lateral_accel_mps2 = _validate_non_negative(
            self.max_lateral_accel_mps2,
            field_name="max_lateral_accel_mps2",
        )
        self.max_vertical_accel_mps2 = _validate_non_negative(
            self.max_vertical_accel_mps2,
            field_name="max_vertical_accel_mps2",
        )


@dataclass
class InterceptGeometry:
    timestamp_s: float
    range_m: float
    closing_speed_mps: float
    line_of_sight_unit: Tuple[float, float, float]
    line_of_sight_rate_rad_s: float
    predicted_time_to_go_s: float
    predicted_miss_distance_m: float
    interceptor_speed_mps: float
    target_speed_mps: float
    predicted_intercept_point: Optional[Tuple[float, float, float]] = None

    def __post_init__(self) -> None:
        self.timestamp_s = _validate_non_negative(self.timestamp_s, field_name="timestamp_s")
        self.range_m = _validate_non_negative(self.range_m, field_name="range_m")
        self.line_of_sight_unit = _validate_vector3(
            self.line_of_sight_unit,
            field_name="line_of_sight_unit",
        )
        self.line_of_sight_rate_rad_s = float(self.line_of_sight_rate_rad_s)
        self.predicted_time_to_go_s = _validate_non_negative(
            self.predicted_time_to_go_s,
            field_name="predicted_time_to_go_s",
        )
        self.predicted_miss_distance_m = _validate_non_negative(
            self.predicted_miss_distance_m,
            field_name="predicted_miss_distance_m",
        )
        self.interceptor_speed_mps = _validate_non_negative(
            self.interceptor_speed_mps,
            field_name="interceptor_speed_mps",
        )
        self.target_speed_mps = _validate_non_negative(
            self.target_speed_mps,
            field_name="target_speed_mps",
        )
        if self.predicted_intercept_point is not None:
            self.predicted_intercept_point = _validate_vector3(
                self.predicted_intercept_point,
                field_name="predicted_intercept_point",
            )


@dataclass
class SteeringCommand:
    phase: GuidancePhase
    lateral_accel_mps2: float = 0.0
    vertical_accel_mps2: float = 0.0
    heading_rate_rad_s: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        self.lateral_accel_mps2 = float(self.lateral_accel_mps2)
        self.vertical_accel_mps2 = float(self.vertical_accel_mps2)
        self.heading_rate_rad_s = float(self.heading_rate_rad_s)
        for field_name in ("lateral_accel_mps2", "vertical_accel_mps2", "heading_rate_rad_s"):
            if not isfinite(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be finite")


@dataclass
class GuidanceSolution:
    interceptor_id: str
    target_id: str
    cycle_number: int
    geometry: InterceptGeometry
    command: SteeringCommand
    phase: GuidancePhase
    state: InterceptorState
    feasible: bool
    abort_reason: str = ""


@dataclass
class InterceptResult:
    interceptor_id: str
    target_id: str
    outcome: str
    miss_distance_m: float
    engagement_time_s: float
    guidance_cycles: int
    final_phase: GuidancePhase
    final_range_m: float
    abort_reason: str = ""
