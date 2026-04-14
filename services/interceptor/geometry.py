"""Intercept geometry computations for guidance laws.

Military context:
This module provides deterministic slant-range and closure geometry used by
the fire-control loop to choose maneuvers under contested conditions.
"""

from __future__ import annotations

from math import sqrt
from typing import Tuple

from services.interceptor.models import InterceptGeometry


def _vector_sub(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vector_add(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vector_scale(v: Tuple[float, float, float], scalar: float) -> Tuple[float, float, float]:
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: Tuple[float, float, float]) -> float:
    return sqrt(_dot(v, v))


class InterceptGeometryComputer:
    """Compute LOS geometry and intercept feasibility metrics."""

    def __init__(self) -> None:
        self._last_time_s = 0.0

    def reset(self) -> None:
        self._last_time_s = 0.0

    def compute(
        self,
        interceptor_pos: Tuple[float, float, float],
        interceptor_vel: Tuple[float, float, float],
        target_pos: Tuple[float, float, float],
        target_vel: Tuple[float, float, float],
        time_s: float,
    ) -> InterceptGeometry:
        rel_pos = _vector_sub(target_pos, interceptor_pos)
        rel_vel = _vector_sub(target_vel, interceptor_vel)
        range_m = max(_norm(rel_pos), 0.0)

        if range_m <= 1e-6:
            los_unit = (0.0, 0.0, 0.0)
            los_rate = 0.0
        else:
            los_unit = _vector_scale(rel_pos, 1.0 / range_m)
            los_rate = _norm(_cross(rel_pos, rel_vel)) / max(range_m * range_m, 1e-6)

        closing_speed = -_dot(rel_vel, los_unit)
        if closing_speed > 1e-3:
            time_to_go_s = range_m / closing_speed
            predicted_interceptor = _vector_add(
                interceptor_pos,
                _vector_scale(interceptor_vel, time_to_go_s),
            )
            predicted_target = _vector_add(target_pos, _vector_scale(target_vel, time_to_go_s))
            predicted_miss = _norm(_vector_sub(predicted_target, predicted_interceptor))
            predicted_intercept_point = predicted_target
        else:
            time_to_go_s = 0.0
            predicted_miss = range_m
            predicted_intercept_point = None

        self._last_time_s = float(time_s)
        return InterceptGeometry(
            timestamp_s=max(float(time_s), 0.0),
            range_m=range_m,
            closing_speed_mps=closing_speed,
            line_of_sight_unit=los_unit,
            line_of_sight_rate_rad_s=los_rate,
            predicted_time_to_go_s=time_to_go_s,
            predicted_miss_distance_m=max(predicted_miss, 0.0),
            interceptor_speed_mps=max(_norm(interceptor_vel), 0.0),
            target_speed_mps=max(_norm(target_vel), 0.0),
            predicted_intercept_point=predicted_intercept_point,
        )
