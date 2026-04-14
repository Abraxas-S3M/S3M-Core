"""Geometry utilities for real-time interceptor guidance.

Military context:
These functions compute the collision triangle and closure metrics used by
command guidance to place an interceptor into a 200-300 m handoff basket.
"""

from __future__ import annotations

from math import acos, asin, degrees, sqrt
from typing import Dict, Optional, Tuple

from services.interceptor.models import InterceptGeometry

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


def _safe_unit(v: Vector3) -> Vector3:
    length = _norm(v)
    if length <= 1e-9:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / length
    return (v[0] * inv, v[1] * inv, v[2] * inv)


def compute_closing_velocity(relative_position_m: Vector3, relative_velocity_mps: Vector3) -> float:
    """Return positive value when interceptor-target range is decreasing."""
    range_m = _norm(relative_position_m)
    if range_m <= 1e-9:
        return 0.0
    return -_dot(relative_position_m, relative_velocity_mps) / range_m


def compute_line_of_sight_rate(relative_position_m: Vector3, relative_velocity_mps: Vector3) -> float:
    """Return scalar LOS angular-rate magnitude in rad/s."""
    range_m = _norm(relative_position_m)
    if range_m <= 1e-9:
        return 0.0
    omega_vec = _cross(relative_position_m, relative_velocity_mps)
    return _norm(omega_vec) / (range_m * range_m)


def predict_miss_distance(relative_position_m: Vector3, relative_velocity_mps: Vector3) -> float:
    """Predict miss distance at closest point of approach (CPA)."""
    rel_speed_sq = _dot(relative_velocity_mps, relative_velocity_mps)
    if rel_speed_sq <= 1e-9:
        return _norm(relative_position_m)
    t_cpa = -_dot(relative_position_m, relative_velocity_mps) / rel_speed_sq
    if t_cpa <= 0.0:
        return _norm(relative_position_m)
    cpa_vector = _add(relative_position_m, _scale(relative_velocity_mps, t_cpa))
    return _norm(cpa_vector)


def estimate_time_to_intercept(
    relative_position_m: Vector3,
    relative_velocity_mps: Vector3,
    interceptor_max_speed_mps: float,
    target_velocity_mps: Optional[Vector3] = None,
) -> Optional[float]:
    """Estimate intercept time using either closure or pursuit quadratic."""
    if interceptor_max_speed_mps <= 0.0:
        return None
    range_m = _norm(relative_position_m)
    if range_m <= 1e-6:
        return 0.0

    if target_velocity_mps is not None:
        vt = target_velocity_mps
        speed_sq = interceptor_max_speed_mps * interceptor_max_speed_mps
        a = _dot(vt, vt) - speed_sq
        b = 2.0 * _dot(relative_position_m, vt)
        c = _dot(relative_position_m, relative_position_m)
        if abs(a) <= 1e-9:
            if abs(b) > 1e-9:
                t = -c / b
                if t > 0.0:
                    return t
        else:
            discriminant = (b * b) - (4.0 * a * c)
            if discriminant >= 0.0:
                root = sqrt(discriminant)
                t1 = (-b - root) / (2.0 * a)
                t2 = (-b + root) / (2.0 * a)
                candidates = [value for value in (t1, t2) if value > 0.0]
                if candidates:
                    return min(candidates)

    closing = compute_closing_velocity(relative_position_m, relative_velocity_mps)
    if closing <= 1e-6:
        return None
    return range_m / closing


def compute_collision_triangle(
    relative_position_m: Vector3,
    target_velocity_mps: Vector3,
    interceptor_max_speed_mps: float,
) -> Dict[str, float]:
    """Compute lead-angle geometry for tactical briefing and debug."""
    range_m = _norm(relative_position_m)
    target_speed = _norm(target_velocity_mps)
    if range_m <= 1e-6:
        return {"range_m": 0.0, "lead_angle_deg": 0.0, "aspect_angle_deg": 0.0}

    los_to_target = _safe_unit(relative_position_m)
    target_unit = _safe_unit(target_velocity_mps)
    cos_aspect = max(-1.0, min(1.0, _dot(los_to_target, target_unit)))
    aspect_angle_rad = acos(cos_aspect)

    lead_angle_deg = 0.0
    if interceptor_max_speed_mps > 1e-6 and target_speed > 1e-6:
        ratio = (target_speed / interceptor_max_speed_mps) * abs(sqrt(max(0.0, 1.0 - (cos_aspect * cos_aspect))))
        ratio = max(-1.0, min(1.0, ratio))
        lead_angle_deg = degrees(asin(ratio))

    return {
        "range_m": range_m,
        "target_speed_mps": target_speed,
        "interceptor_speed_mps": max(0.0, interceptor_max_speed_mps),
        "aspect_angle_deg": degrees(aspect_angle_rad),
        "lead_angle_deg": lead_angle_deg,
    }


def compute_intercept_geometry(
    interceptor_position_m: Vector3,
    interceptor_velocity_mps: Vector3,
    target_position_m: Vector3,
    target_velocity_mps: Vector3,
    interceptor_max_speed_mps: float,
) -> InterceptGeometry:
    """Compute full geometry packet for one guidance-cycle update."""
    relative_position = _sub(target_position_m, interceptor_position_m)
    relative_velocity = _sub(target_velocity_mps, interceptor_velocity_mps)
    range_m = _norm(relative_position)
    los_unit = _safe_unit(relative_position)
    closing_velocity = compute_closing_velocity(relative_position, relative_velocity)
    los_rate = compute_line_of_sight_rate(relative_position, relative_velocity)
    miss_distance = predict_miss_distance(relative_position, relative_velocity)
    tti = estimate_time_to_intercept(
        relative_position,
        relative_velocity,
        interceptor_max_speed_mps,
        target_velocity_mps=target_velocity_mps,
    )
    triangle = compute_collision_triangle(
        relative_position,
        target_velocity_mps,
        interceptor_max_speed_mps,
    )
    return InterceptGeometry(
        range_m=range_m,
        closing_velocity_mps=closing_velocity,
        line_of_sight_rate_rad_s=los_rate,
        predicted_miss_distance_m=miss_distance,
        relative_position_m=relative_position,
        relative_velocity_mps=relative_velocity,
        line_of_sight_unit=los_unit,
        time_to_intercept_s=tti,
        collision_triangle=triangle,
    )
