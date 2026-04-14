"""Guidance law implementations for interceptor steering.

Military context:
The guidance laws encode tactical steering behavior for command-guided
interceptors across boost, midcourse, and terminal phases.
"""

from __future__ import annotations

from math import atan2, copysign, hypot, pi, sin, sqrt
from typing import Tuple

from services.interceptor.models import GuidancePhase, InterceptGeometry, InterceptorConfig, SteeringCommand


def _vector_sub(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vector_add(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vector_scale(v: Tuple[float, float, float], scalar: float) -> Tuple[float, float, float]:
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: Tuple[float, float, float]) -> float:
    return sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _heading_xy(vector: Tuple[float, float, float]) -> float:
    return atan2(vector[1], vector[0]) if hypot(vector[0], vector[1]) > 1e-9 else 0.0


def _wrap_angle(angle_rad: float) -> float:
    wrapped = (angle_rad + pi) % (2.0 * pi) - pi
    return wrapped


def _build_command(
    *,
    phase: GuidancePhase,
    lateral_accel: float,
    vertical_accel: float,
    heading_rate: float,
    config: InterceptorConfig,
    notes: str,
) -> SteeringCommand:
    return SteeringCommand(
        phase=phase,
        lateral_accel_mps2=_clamp(
            lateral_accel,
            -config.max_lateral_accel_mps2,
            config.max_lateral_accel_mps2,
        ),
        vertical_accel_mps2=_clamp(
            vertical_accel,
            -config.max_vertical_accel_mps2,
            config.max_vertical_accel_mps2,
        ),
        heading_rate_rad_s=_clamp(heading_rate, -2.5, 2.5),
        notes=notes,
    )


class PurePursuit:
    """Classic pure pursuit guidance with bounded acceleration commands."""

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase,
    ) -> SteeringCommand:
        del geometry
        los = _vector_sub(target_pos, interceptor_pos)
        desired_heading = _heading_xy(los)
        heading_error = _wrap_angle(desired_heading - 0.0)
        lateral_accel = config.max_lateral_accel_mps2 * sin(heading_error)
        vertical_ratio = 0.0 if abs(los[2]) < 1e-9 else los[2] / max(_norm(los), 1e-6)
        vertical_accel = config.max_vertical_accel_mps2 * vertical_ratio

        return _build_command(
            phase=phase,
            lateral_accel=lateral_accel,
            vertical_accel=vertical_accel,
            heading_rate=heading_error * 1.2,
            config=config,
            notes="Pure pursuit toward current target LOS",
        )


class LeadPursuit:
    """Lead pursuit guidance that points at predicted target position."""

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase,
    ) -> SteeringCommand:
        interceptor_speed = max(geometry.interceptor_speed_mps, 1.0)
        lead_time_s = geometry.range_m / interceptor_speed
        lead_point = _vector_add(target_pos, _vector_scale(target_vel, lead_time_s))
        lead_los = _vector_sub(lead_point, interceptor_pos)
        desired_heading = _heading_xy(lead_los)
        heading_error = _wrap_angle(desired_heading - 0.0)
        lateral_accel = config.max_lateral_accel_mps2 * sin(heading_error)
        vertical_ratio = 0.0 if abs(lead_los[2]) < 1e-9 else lead_los[2] / max(_norm(lead_los), 1e-6)
        vertical_accel = config.max_vertical_accel_mps2 * vertical_ratio

        return _build_command(
            phase=phase,
            lateral_accel=lateral_accel,
            vertical_accel=vertical_accel,
            heading_rate=heading_error * 1.4,
            config=config,
            notes="Lead pursuit toward extrapolated target point",
        )


class ProportionalNavigation:
    """Proportional navigation guidance (default Krechet mode)."""

    def compute(
        self,
        geometry: InterceptGeometry,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
        config: InterceptorConfig,
        phase: GuidancePhase,
    ) -> SteeringCommand:
        del interceptor_pos, target_pos
        rel_vel = _vector_sub(target_vel, interceptor_vel)
        turn_axis = _cross(geometry.line_of_sight_unit, rel_vel)
        turn_sign = 1.0 if abs(turn_axis[2]) < 1e-9 else copysign(1.0, turn_axis[2])

        # Tactical context: PN scales turn command by LOS rate and closure,
        # creating aggressive late-course maneuvering against maneuvering threats.
        lateral_magnitude = (
            config.nav_constant
            * max(geometry.closing_speed_mps, 0.0)
            * abs(geometry.line_of_sight_rate_rad_s)
        )
        lateral_accel = turn_sign * lateral_magnitude
        heading_rate = turn_sign * (lateral_magnitude / max(geometry.interceptor_speed_mps, 1.0))

        vertical_bias = geometry.line_of_sight_unit[2] * config.max_vertical_accel_mps2
        vertical_accel = vertical_bias + (0.1 * lateral_magnitude * copysign(1.0, vertical_bias or 1.0))

        return _build_command(
            phase=phase,
            lateral_accel=lateral_accel,
            vertical_accel=vertical_accel,
            heading_rate=heading_rate,
            config=config,
            notes="PN command based on LOS rate and closure",
        )
