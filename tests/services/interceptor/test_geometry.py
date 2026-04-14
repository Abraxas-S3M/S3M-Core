from __future__ import annotations

import pytest

from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.models import InterceptGeometry


def test_compute_nominal_tail_chase_solution() -> None:
    computer = InterceptGeometryComputer()
    geometry = computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(300.0, 0.0, 0.0),
        target_pos=(1000.0, 0.0, 0.0),
        target_vel=(200.0, 0.0, 0.0),
        time_s=1.0,
    )

    assert geometry.range_m == pytest.approx(1000.0)
    assert geometry.closing_velocity_mps == pytest.approx(100.0)
    assert geometry.time_to_intercept_s == pytest.approx(10.0)
    assert geometry.line_of_sight_az_deg == pytest.approx(90.0)
    assert geometry.line_of_sight_el_deg == pytest.approx(0.0)
    assert geometry.los_rate_az_dps == pytest.approx(0.0)
    assert geometry.predicted_miss_distance_m == pytest.approx(0.0)
    assert geometry.aspect_angle_deg == pytest.approx(180.0)
    assert geometry.crossing_angle_deg == pytest.approx(0.0)


def test_compute_handles_azimuth_wrap_for_los_rate() -> None:
    computer = InterceptGeometryComputer()

    computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(-0.017452406, 0.999847695, 0.0),  # 359 degrees
        target_vel=(0.0, 0.0, 0.0),
        time_s=0.0,
    )
    geometry = computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(0.017452406, 0.999847695, 0.0),  # 1 degree
        target_vel=(0.0, 0.0, 0.0),
        time_s=1.0,
    )

    assert geometry.line_of_sight_az_deg == pytest.approx(1.0, abs=1e-3)
    assert geometry.los_rate_az_dps == pytest.approx(2.0, abs=1e-3)
    assert geometry.los_rate_el_dps == pytest.approx(0.0)


def test_reset_clears_los_rate_history() -> None:
    computer = InterceptGeometryComputer()
    computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(10.0, 0.0, 0.0),
        target_vel=(0.0, 0.0, 0.0),
        time_s=0.0,
    )
    computer.reset()
    geometry = computer.compute(
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(0.0, 10.0, 0.0),
        target_vel=(0.0, 0.0, 0.0),
        time_s=1.0,
    )

    assert geometry.los_rate_az_dps == pytest.approx(0.0)
    assert geometry.los_rate_el_dps == pytest.approx(0.0)


def test_compute_rejects_invalid_input_vectors() -> None:
    computer = InterceptGeometryComputer()

    with pytest.raises(ValueError, match="interceptor_pos must be a 3-element sequence"):
        computer.compute(
            interceptor_pos=(0.0, 0.0),  # type: ignore[arg-type]
            interceptor_vel=(0.0, 0.0, 0.0),
            target_pos=(1.0, 1.0, 1.0),
            target_vel=(0.0, 0.0, 0.0),
            time_s=0.0,
        )


def test_model_validates_angle_ranges() -> None:
    with pytest.raises(ValueError, match="line_of_sight_el_deg must be between -90 and 90"):
        InterceptGeometry(
            range_m=100.0,
            closing_velocity_mps=120.0,
            time_to_intercept_s=1.0,
            line_of_sight_az_deg=0.0,
            line_of_sight_el_deg=91.0,
            los_rate_az_dps=0.0,
            los_rate_el_dps=0.0,
            lead_angle_deg=0.0,
            predicted_miss_distance_m=0.0,
            aspect_angle_deg=0.0,
            crossing_angle_deg=0.0,
        )
