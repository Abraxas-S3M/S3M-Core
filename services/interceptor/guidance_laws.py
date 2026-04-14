"""Guidance law implementations for interceptor steering commands.

Military context:
Implements layered pursuit laws used by C2 during midcourse guidance before
autonomous seeker lock in the terminal basket.
"""

from __future__ import annotations

from math import atan2, degrees, sqrt
from typing import Tuple

from services.interceptor.models import GuidanceMode, InterceptGeometry, InterceptorConfig, SteeringCommand

Vector3 = Tuple[float, float, float]


def _dot(a: Vector3, b: Vector3) -> float:
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _norm(v: Vector3) -> float:
    return sqrt(_dot(v, v))


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(v: Vector3, s: float) -> Vector3:
    return (v[0] * s, v[1] * s, v[2] * s)


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    )


def _unit(v: Vector3) -> Vector3:
    length = _norm(v)
    if length <= 1e-9:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / length
    return (v[0] * inv, v[1] * inv, v[2] * inv)


def _clip_norm(v: Vector3, max_mag: float) -> Vector3:
    magnitude = _norm(v)
    if magnitude <= max_mag or magnitude <= 1e-9:
        return v
    factor = max_mag / magnitude
    return _scale(v, factor)


def _heading_pitch_from_velocity(velocity_mps: Vector3) -> Tuple[float, float]:
    vx, vy, vz = velocity_mps
    horizontal = sqrt((vx * vx) + (vy * vy))
    heading_deg = degrees(atan2(vy, vx)) if horizontal > 1e-9 else 0.0
    pitch_deg = degrees(atan2(vz, horizontal)) if (horizontal > 1e-9 or abs(vz) > 1e-9) else 0.0
    return heading_deg, pitch_deg


def _desired_speed(config: InterceptorConfig, geometry: InterceptGeometry) -> float:
    if geometry.range_m > config.terminal_approach_range_m:
        return config.max_speed_mps
    return max(0.5 * config.max_speed_mps, 0.6 * geometry.closing_velocity_mps)


def _command_from_desired_velocity(
    mode: GuidanceMode,
    interceptor_velocity_mps: Vector3,
    desired_velocity_mps: Vector3,
    config: InterceptorConfig,
    dt_s: float,
) -> SteeringCommand:
    clipped_desired_velocity = _clip_norm(desired_velocity_mps, config.max_speed_mps)
    safe_dt = max(1e-3, dt_s)
    raw_accel = _scale(_sub(clipped_desired_velocity, interceptor_velocity_mps), 1.0 / safe_dt)
    clipped_accel = _clip_norm(raw_accel, config.max_acceleration_mps2)
    heading_deg, pitch_deg = _heading_pitch_from_velocity(clipped_desired_velocity)
    throttle = min(1.0, _norm(clipped_desired_velocity) / max(1e-3, config.max_speed_mps))
    return SteeringCommand(
        acceleration_mps2=clipped_accel,
        desired_velocity_mps=clipped_desired_velocity,
        commanded_heading_deg=heading_deg,
        commanded_pitch_deg=pitch_deg,
        throttle_fraction=throttle,
        mode=mode,
    )


def pure_pursuit_command(
    interceptor_velocity_mps: Vector3,
    geometry: InterceptGeometry,
    config: InterceptorConfig,
    dt_s: float,
) -> SteeringCommand:
    """Always point interceptor velocity vector directly at current target LOS."""
    los_unit = geometry.line_of_sight_unit
    speed = _desired_speed(config, geometry)
    desired_velocity = _scale(los_unit, speed)
    return _command_from_desired_velocity(
        GuidanceMode.PURE_PURSUIT,
        interceptor_velocity_mps,
        desired_velocity,
        config,
        dt_s,
    )


def lead_pursuit_command(
    interceptor_velocity_mps: Vector3,
    target_velocity_mps: Vector3,
    geometry: InterceptGeometry,
    config: InterceptorConfig,
    dt_s: float,
) -> SteeringCommand:
    """Aim ahead of target based on estimated time-to-go."""
    lead_time = geometry.time_to_intercept_s
    if lead_time is None:
        closing = max(1.0, geometry.closing_velocity_mps)
        lead_time = geometry.range_m / closing
    lead_time = max(0.0, min(20.0, lead_time * config.lead_bias))
    lead_vector = _add(geometry.relative_position_m, _scale(target_velocity_mps, lead_time))
    desired_direction = _unit(lead_vector)
    if desired_direction == (0.0, 0.0, 0.0):
        desired_direction = geometry.line_of_sight_unit
    speed = _desired_speed(config, geometry)
    desired_velocity = _scale(desired_direction, speed)
    return _command_from_desired_velocity(
        GuidanceMode.LEAD_PURSUIT,
        interceptor_velocity_mps,
        desired_velocity,
        config,
        dt_s,
    )


def proportional_navigation_command(
    interceptor_velocity_mps: Vector3,
    geometry: InterceptGeometry,
    config: InterceptorConfig,
    dt_s: float,
) -> SteeringCommand:
    """Apply PN law: lateral acceleration ~ N * Vc * LOS_rate."""
    relative_position = geometry.relative_position_m
    relative_velocity = geometry.relative_velocity_mps
    range_sq = _dot(relative_position, relative_position)
    los_unit = geometry.line_of_sight_unit
    closing = max(0.0, geometry.closing_velocity_mps)

    if range_sq <= 1e-9 or closing <= 1e-6:
        return pure_pursuit_command(interceptor_velocity_mps, geometry, config, dt_s)

    # Tactical PN core: rotate velocity to null LOS rotation while preserving closure.
    omega = _scale(_cross(relative_position, relative_velocity), 1.0 / range_sq)
    lateral_accel = _scale(_cross(omega, los_unit), config.navigation_constant * closing)
    forward_bias = _scale(los_unit, 0.15 * config.max_acceleration_mps2)
    accel_vector = _clip_norm(_add(lateral_accel, forward_bias), config.max_acceleration_mps2)
    desired_velocity = _add(interceptor_velocity_mps, _scale(accel_vector, max(dt_s, 1e-3)))
    desired_velocity = _clip_norm(desired_velocity, config.max_speed_mps)
    if _norm(desired_velocity) <= 1e-6:
        desired_velocity = _scale(los_unit, min(config.max_speed_mps, max(1.0, closing)))
    return _command_from_desired_velocity(
        GuidanceMode.PROPORTIONAL_NAVIGATION,
        interceptor_velocity_mps,
        desired_velocity,
        config,
        dt_s,
    )


def compute_guidance_command(
    mode: GuidanceMode,
    interceptor_velocity_mps: Vector3,
    target_velocity_mps: Vector3,
    geometry: InterceptGeometry,
    config: InterceptorConfig,
    dt_s: float,
) -> SteeringCommand:
    """Dispatch to selected guidance law implementation."""
    if mode == GuidanceMode.PURE_PURSUIT:
        return pure_pursuit_command(interceptor_velocity_mps, geometry, config, dt_s)
    if mode == GuidanceMode.LEAD_PURSUIT:
        return lead_pursuit_command(interceptor_velocity_mps, target_velocity_mps, geometry, config, dt_s)
    return proportional_navigation_command(interceptor_velocity_mps, geometry, config, dt_s)
