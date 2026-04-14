"""Data models for interceptor guidance computations.

Military context:
These structures carry the validated geometry and steering commands used by
the interceptor autopilot loop. Input validation is strict because malformed
kinematics in tactical guidance code can create unsafe steering behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Tuple


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _validate_vec3(value: Tuple[float, float, float], *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-tuple")
    return (
        _validate_finite(value[0], field_name=f"{field_name}[0]"),
        _validate_finite(value[1], field_name=f"{field_name}[1]"),
        _validate_finite(value[2], field_name=f"{field_name}[2]"),
    )


class GuidanceMode(str, Enum):
    PURE_PURSUIT = "pure_pursuit"
    LEAD_PURSUIT = "lead_pursuit"
    PROPORTIONAL_NAV = "proportional_nav"


class GuidancePhase(str, Enum):
    BOOST = "boost"
    MIDCOURSE = "midcourse"
    TERMINAL = "terminal"


@dataclass
class InterceptGeometry:
    """Relative interceptor-target geometry at one guidance update."""

    range_m: float
    closing_velocity_mps: float
    los_az_deg: float = 0.0
    los_el_deg: float = 0.0
    los_rate_az_dps: float = 0.0
    los_rate_el_dps: float = 0.0
    time_to_intercept_s: float = 0.0

    def __post_init__(self) -> None:
        self.range_m = _validate_finite(self.range_m, field_name="range_m")
        self.closing_velocity_mps = _validate_finite(
            self.closing_velocity_mps,
            field_name="closing_velocity_mps",
        )
        self.los_az_deg = _validate_finite(self.los_az_deg, field_name="los_az_deg")
        self.los_el_deg = _validate_finite(self.los_el_deg, field_name="los_el_deg")
        self.los_rate_az_dps = _validate_finite(self.los_rate_az_dps, field_name="los_rate_az_dps")
        self.los_rate_el_dps = _validate_finite(self.los_rate_el_dps, field_name="los_rate_el_dps")
        self.time_to_intercept_s = _validate_finite(
            self.time_to_intercept_s,
            field_name="time_to_intercept_s",
        )
        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
        if self.time_to_intercept_s < 0.0:
            raise ValueError("time_to_intercept_s must be non-negative")


@dataclass
class InterceptorConfig:
    """Autopilot and kinematic limits for interceptor guidance."""

    max_speed_mps: float = 250.0
    max_acceleration_mps2: float = 35.0
    nav_constant: float = 3.5
    guidance_update_hz: float = 20.0

    def __post_init__(self) -> None:
        self.max_speed_mps = _validate_finite(self.max_speed_mps, field_name="max_speed_mps")
        self.max_acceleration_mps2 = _validate_finite(
            self.max_acceleration_mps2,
            field_name="max_acceleration_mps2",
        )
        self.nav_constant = _validate_finite(self.nav_constant, field_name="nav_constant")
        self.guidance_update_hz = _validate_finite(
            self.guidance_update_hz,
            field_name="guidance_update_hz",
        )
        if self.max_speed_mps <= 0.0:
            raise ValueError("max_speed_mps must be positive")
        if self.max_acceleration_mps2 <= 0.0:
            raise ValueError("max_acceleration_mps2 must be positive")
        if self.nav_constant <= 0.0:
            raise ValueError("nav_constant must be positive")
        if self.guidance_update_hz <= 0.0:
            raise ValueError("guidance_update_hz must be positive")


@dataclass
class SteeringCommand:
    """Autopilot steering command emitted by a guidance law."""

    commanded_heading_deg: float
    commanded_pitch_deg: float
    commanded_speed_mps: float
    commanded_position: Tuple[float, float, float]
    lateral_accel_mps2: float = 0.0
    vertical_accel_mps2: float = 0.0
    guidance_mode: GuidanceMode = GuidanceMode.PURE_PURSUIT
    phase: GuidancePhase = GuidancePhase.MIDCOURSE

    def __post_init__(self) -> None:
        self.commanded_heading_deg = (
            _validate_finite(self.commanded_heading_deg, field_name="commanded_heading_deg") % 360.0
        )
        self.commanded_pitch_deg = _validate_finite(
            self.commanded_pitch_deg,
            field_name="commanded_pitch_deg",
        )
        self.commanded_speed_mps = _validate_finite(
            self.commanded_speed_mps,
            field_name="commanded_speed_mps",
        )
        self.commanded_position = _validate_vec3(
            self.commanded_position,
            field_name="commanded_position",
        )
        self.lateral_accel_mps2 = _validate_finite(
            self.lateral_accel_mps2,
            field_name="lateral_accel_mps2",
        )
        self.vertical_accel_mps2 = _validate_finite(
            self.vertical_accel_mps2,
            field_name="vertical_accel_mps2",
        )
        if self.commanded_speed_mps < 0.0:
            raise ValueError("commanded_speed_mps must be non-negative")
