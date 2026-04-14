"""Data models for interceptor guidance and engagement decisions.

Military context:
These structures represent the command-post guidance state used to drive an
interceptor UAV from launch through 200-300 m handoff and terminal engagement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _validate_non_negative(value: float, *, field_name: str) -> float:
    parsed = _validate_finite(value, field_name=field_name)
    if parsed < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


def _validate_vec3(value: Tuple[float, float, float], *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-tuple")
    return (
        _validate_finite(value[0], field_name=f"{field_name}[0]"),
        _validate_finite(value[1], field_name=f"{field_name}[1]"),
        _validate_finite(value[2], field_name=f"{field_name}[2]"),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterceptorState(str, Enum):
    PRELAUNCH = "prelaunch"
    LAUNCHED = "launched"
    RADAR_ACQUIRED = "radar_acquired"
    MIDCOURSE_GUIDED = "midcourse_guided"
    TERMINAL_APPROACH = "terminal_approach"
    AUTONOMOUS_HANDOFF = "autonomous_handoff"
    ENGAGED = "engaged"
    MISS = "miss"
    ABORTED = "aborted"


class GuidancePhase(str, Enum):
    PRELAUNCH = "prelaunch"
    MIDCOURSE_GUIDED = "midcourse_guided"
    TERMINAL_APPROACH = "terminal_approach"
    AUTONOMOUS_HANDOFF = "autonomous_handoff"
    ENGAGED = "engaged"
    MISS = "miss"


class GuidanceMode(str, Enum):
    PURE_PURSUIT = "pure_pursuit"
    LEAD_PURSUIT = "lead_pursuit"
    PROPORTIONAL_NAVIGATION = "proportional_navigation"


@dataclass
class HandoffCriteria:
    min_range_m: float = 200.0
    max_range_m: float = 300.0
    max_line_of_sight_rate_rad_s: float = 0.35
    min_closing_velocity_mps: float = 5.0

    def __post_init__(self) -> None:
        self.min_range_m = _validate_non_negative(self.min_range_m, field_name="min_range_m")
        self.max_range_m = _validate_non_negative(self.max_range_m, field_name="max_range_m")
        if self.max_range_m < self.min_range_m:
            raise ValueError("max_range_m must be >= min_range_m")
        self.max_line_of_sight_rate_rad_s = _validate_non_negative(
            self.max_line_of_sight_rate_rad_s,
            field_name="max_line_of_sight_rate_rad_s",
        )
        self.min_closing_velocity_mps = _validate_non_negative(
            self.min_closing_velocity_mps,
            field_name="min_closing_velocity_mps",
        )


@dataclass
class InterceptGeometry:
    range_m: float
    closing_velocity_mps: float
    line_of_sight_rate_rad_s: float
    predicted_miss_distance_m: float
    relative_position_m: Tuple[float, float, float]
    relative_velocity_mps: Tuple[float, float, float]
    line_of_sight_unit: Tuple[float, float, float]
    time_to_intercept_s: Optional[float] = None
    collision_triangle: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        self.range_m = _validate_non_negative(self.range_m, field_name="range_m")
        self.closing_velocity_mps = _validate_finite(
            self.closing_velocity_mps,
            field_name="closing_velocity_mps",
        )
        self.line_of_sight_rate_rad_s = _validate_non_negative(
            self.line_of_sight_rate_rad_s,
            field_name="line_of_sight_rate_rad_s",
        )
        self.predicted_miss_distance_m = _validate_non_negative(
            self.predicted_miss_distance_m,
            field_name="predicted_miss_distance_m",
        )
        self.relative_position_m = _validate_vec3(self.relative_position_m, field_name="relative_position_m")
        self.relative_velocity_mps = _validate_vec3(self.relative_velocity_mps, field_name="relative_velocity_mps")
        self.line_of_sight_unit = _validate_vec3(self.line_of_sight_unit, field_name="line_of_sight_unit")
        if self.time_to_intercept_s is not None:
            self.time_to_intercept_s = _validate_non_negative(
                self.time_to_intercept_s,
                field_name="time_to_intercept_s",
            )
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            self.timestamp = self.timestamp.astimezone(timezone.utc)


@dataclass
class SteeringCommand:
    acceleration_mps2: Tuple[float, float, float]
    desired_velocity_mps: Tuple[float, float, float]
    commanded_heading_deg: float
    commanded_pitch_deg: float
    throttle_fraction: float = 0.5
    mode: GuidanceMode = GuidanceMode.PROPORTIONAL_NAVIGATION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.acceleration_mps2 = _validate_vec3(self.acceleration_mps2, field_name="acceleration_mps2")
        self.desired_velocity_mps = _validate_vec3(self.desired_velocity_mps, field_name="desired_velocity_mps")
        self.commanded_heading_deg = _validate_finite(self.commanded_heading_deg, field_name="commanded_heading_deg")
        self.commanded_pitch_deg = _validate_finite(self.commanded_pitch_deg, field_name="commanded_pitch_deg")
        self.throttle_fraction = _validate_finite(self.throttle_fraction, field_name="throttle_fraction")
        if not (0.0 <= self.throttle_fraction <= 1.0):
            raise ValueError("throttle_fraction must be in [0.0, 1.0]")
        if isinstance(self.mode, str):
            self.mode = GuidanceMode(self.mode)


@dataclass
class InterceptorConfig:
    interceptor_type: str
    name_en: str
    name_ar: str
    max_speed_mps: float
    max_acceleration_mps2: float
    update_rate_hz: float = 20.0
    navigation_constant: float = 3.0
    lead_bias: float = 1.0
    terminal_approach_range_m: float = 1_200.0
    autonomous_engagement_range_m: float = 10.0
    miss_abort_distance_m: float = 600.0
    preferred_mode: GuidanceMode = GuidanceMode.PROPORTIONAL_NAVIGATION
    handoff_criteria: HandoffCriteria = field(default_factory=HandoffCriteria)

    def __post_init__(self) -> None:
        if not self.interceptor_type:
            raise ValueError("interceptor_type is required")
        if not self.name_en:
            raise ValueError("name_en is required")
        if not self.name_ar:
            raise ValueError("name_ar is required")
        self.max_speed_mps = _validate_non_negative(self.max_speed_mps, field_name="max_speed_mps")
        self.max_acceleration_mps2 = _validate_non_negative(
            self.max_acceleration_mps2,
            field_name="max_acceleration_mps2",
        )
        self.update_rate_hz = _validate_non_negative(self.update_rate_hz, field_name="update_rate_hz")
        if self.update_rate_hz <= 0.0:
            raise ValueError("update_rate_hz must be > 0")
        self.navigation_constant = _validate_non_negative(
            self.navigation_constant,
            field_name="navigation_constant",
        )
        self.lead_bias = _validate_non_negative(self.lead_bias, field_name="lead_bias")
        self.terminal_approach_range_m = _validate_non_negative(
            self.terminal_approach_range_m,
            field_name="terminal_approach_range_m",
        )
        self.autonomous_engagement_range_m = _validate_non_negative(
            self.autonomous_engagement_range_m,
            field_name="autonomous_engagement_range_m",
        )
        self.miss_abort_distance_m = _validate_non_negative(
            self.miss_abort_distance_m,
            field_name="miss_abort_distance_m",
        )
        if isinstance(self.preferred_mode, str):
            self.preferred_mode = GuidanceMode(self.preferred_mode)


@dataclass
class GuidanceSolution:
    interceptor_id: str
    target_id: str
    phase: GuidancePhase
    mode: GuidanceMode
    geometry: InterceptGeometry
    steering_command: SteeringCommand
    handoff_recommended: bool
    abort_recommended: bool
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)
    solution_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        if not self.target_id:
            raise ValueError("target_id is required")
        if isinstance(self.phase, str):
            self.phase = GuidancePhase(self.phase)
        if isinstance(self.mode, str):
            self.mode = GuidanceMode(self.mode)
        if not isinstance(self.geometry, InterceptGeometry):
            raise ValueError("geometry must be InterceptGeometry")
        if not isinstance(self.steering_command, SteeringCommand):
            raise ValueError("steering_command must be SteeringCommand")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "solution_id": self.solution_id,
            "interceptor_id": self.interceptor_id,
            "target_id": self.target_id,
            "phase": self.phase.value,
            "mode": self.mode.value,
            "range_m": self.geometry.range_m,
            "closing_velocity_mps": self.geometry.closing_velocity_mps,
            "predicted_miss_distance_m": self.geometry.predicted_miss_distance_m,
            "handoff_recommended": self.handoff_recommended,
            "abort_recommended": self.abort_recommended,
            "reason": self.reason,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
        }


@dataclass
class InterceptResult:
    interceptor_id: str
    target_id: str
    state: InterceptorState
    miss_distance_m: float
    engagement_range_m: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.interceptor_id:
            raise ValueError("interceptor_id is required")
        if not self.target_id:
            raise ValueError("target_id is required")
        if isinstance(self.state, str):
            self.state = InterceptorState(self.state)
        self.miss_distance_m = _validate_non_negative(self.miss_distance_m, field_name="miss_distance_m")
        self.engagement_range_m = _validate_non_negative(
            self.engagement_range_m,
            field_name="engagement_range_m",
        )
