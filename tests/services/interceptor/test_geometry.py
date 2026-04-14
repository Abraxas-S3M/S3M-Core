"""Unit tests for interceptor geometry calculations.

Military context:
Geometry correctness is critical because every downstream steering decision
depends on accurate closure and miss-distance estimates.
"""

from __future__ import annotations

from services.interceptor.geometry import InterceptGeometryComputer


def test_compute_geometry_for_closing_target() -> None:
    computer = InterceptGeometryComputer()
    geometry = computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(200.0, 0.0, 0.0),
        target_pos=(2_000.0, 200.0, 50.0),
        target_vel=(-50.0, 0.0, 0.0),
        time_s=0.1,
    )

    assert geometry.range_m > 0.0
    assert geometry.closing_speed_mps > 0.0
    assert geometry.predicted_time_to_go_s > 0.0
    assert geometry.predicted_intercept_point is not None


def test_compute_geometry_for_opening_target_returns_zero_time_to_go() -> None:
    computer = InterceptGeometryComputer()
    geometry = computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(100.0, 0.0, 0.0),
        target_pos=(500.0, 0.0, 0.0),
        target_vel=(300.0, 0.0, 0.0),
        time_s=0.2,
    )

    assert geometry.closing_speed_mps < 0.0
    assert geometry.predicted_time_to_go_s == 0.0
    assert geometry.predicted_intercept_point is None
    assert geometry.predicted_miss_distance_m == geometry.range_m
