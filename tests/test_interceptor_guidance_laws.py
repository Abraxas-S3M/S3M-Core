"""Unit tests for interceptor guidance law implementations.

Military context:
Tests verify deterministic steering outputs for pure/lead pursuit and
proportional navigation so command-and-control can trust autopilot behavior.
"""

from __future__ import annotations

import pytest

from services.interceptor.guidance_laws import LeadPursuit, ProportionalNavigation, PurePursuit
from services.interceptor.models import GuidanceMode, InterceptGeometry, InterceptorConfig


def _geometry(**overrides: float) -> InterceptGeometry:
    baseline = {
        "range_m": 2_500.0,
        "closing_velocity_mps": 220.0,
        "los_az_deg": 0.0,
        "los_el_deg": 0.0,
        "los_rate_az_dps": 0.0,
        "los_rate_el_dps": 0.0,
        "time_to_intercept_s": 8.0,
    }
    baseline.update(overrides)
    return InterceptGeometry(**baseline)


def _config(**overrides: float) -> InterceptorConfig:
    baseline = {
        "max_speed_mps": 260.0,
        "max_acceleration_mps2": 30.0,
        "nav_constant": 4.0,
        "guidance_update_hz": 20.0,
    }
    baseline.update(overrides)
    return InterceptorConfig(**baseline)


def test_pure_pursuit_points_directly_at_target() -> None:
    law = PurePursuit()
    cmd = law.compute(
        geometry=_geometry(),
        interceptor_pos=(0.0, 0.0, 1_000.0),
        target_pos=(1_000.0, 0.0, 1_000.0),
        config=_config(max_speed_mps=200.0),
    )

    assert cmd.guidance_mode is GuidanceMode.PURE_PURSUIT
    assert cmd.commanded_heading_deg == pytest.approx(90.0)
    assert cmd.commanded_pitch_deg == pytest.approx(0.0)
    assert cmd.commanded_speed_mps == pytest.approx(200.0)
    assert cmd.commanded_position == (1_000.0, 0.0, 1_000.0)


def test_lead_pursuit_extrapolates_with_time_to_go() -> None:
    law = LeadPursuit()
    cmd = law.compute(
        geometry=_geometry(time_to_intercept_s=5.0),
        interceptor_pos=(0.0, 0.0, 0.0),
        target_pos=(0.0, 1_000.0, 100.0),
        target_vel=(10.0, 0.0, -2.0),
        config=_config(),
    )

    assert cmd.guidance_mode is GuidanceMode.LEAD_PURSUIT
    assert cmd.commanded_position == (50.0, 1_000.0, 90.0)


def test_lead_pursuit_caps_prediction_horizon() -> None:
    law = LeadPursuit()
    cmd = law.compute(
        geometry=_geometry(time_to_intercept_s=120.0),
        interceptor_pos=(0.0, 0.0, 0.0),
        target_pos=(10.0, 0.0, 0.0),
        target_vel=(2.0, 0.0, 0.0),
        config=_config(),
    )

    # Tactical safeguard: cap long extrapolation horizons to avoid runaway lead points.
    assert cmd.commanded_position == (130.0, 0.0, 0.0)


def test_proportional_navigation_clamps_high_acceleration() -> None:
    law = ProportionalNavigation()
    cmd = law.compute(
        geometry=_geometry(closing_velocity_mps=300.0, los_rate_az_dps=35.0, los_rate_el_dps=-35.0),
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 140.0, 0.0),
        target_pos=(2_000.0, 0.0, 200.0),
        target_vel=(0.0, -160.0, 0.0),
        config=_config(max_acceleration_mps2=18.0),
    )

    assert cmd.guidance_mode is GuidanceMode.PROPORTIONAL_NAV
    assert cmd.lateral_accel_mps2 == pytest.approx(18.0)
    assert cmd.vertical_accel_mps2 == pytest.approx(-18.0)
    assert -60.0 <= cmd.commanded_pitch_deg <= 60.0


def test_proportional_navigation_increases_speed_toward_max() -> None:
    law = ProportionalNavigation()
    cmd = law.compute(
        geometry=_geometry(los_rate_az_dps=1.0, los_rate_el_dps=0.5),
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 100.0, 0.0),
        target_pos=(1_000.0, 1_000.0, 100.0),
        target_vel=(0.0, -100.0, 0.0),
        config=_config(max_speed_mps=101.0),
    )

    assert cmd.commanded_speed_mps == pytest.approx(101.0)
    assert cmd.commanded_position != (0.0, 0.0, 0.0)
