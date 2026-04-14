"""Unit tests for interceptor guidance laws.

Military context:
These checks ensure steering commands stay bounded while preserving doctrinal
behavior for pursuit and proportional navigation.
"""

from __future__ import annotations

from services.interceptor.guidance_laws import LeadPursuit, ProportionalNavigation, PurePursuit
from services.interceptor.models import GuidancePhase, InterceptGeometry, InterceptorConfig


def _config() -> InterceptorConfig:
    return InterceptorConfig(
        interceptor_id="int-1",
        guidance_update_hz=10.0,
        nav_constant=4.0,
        max_lateral_accel_mps2=30.0,
        max_vertical_accel_mps2=20.0,
    )


def _geometry(*, los_rate: float = 0.04, closing_speed: float = 150.0) -> InterceptGeometry:
    return InterceptGeometry(
        timestamp_s=0.2,
        range_m=1_000.0,
        closing_speed_mps=closing_speed,
        line_of_sight_unit=(0.98, 0.2, 0.05),
        line_of_sight_rate_rad_s=los_rate,
        predicted_time_to_go_s=5.0,
        predicted_miss_distance_m=20.0,
        interceptor_speed_mps=250.0,
        target_speed_mps=180.0,
    )


def test_pure_pursuit_generates_bounded_command() -> None:
    command = PurePursuit().compute(
        geometry=_geometry(),
        interceptor_pos=(0.0, 0.0, 0.0),
        target_pos=(500.0, 400.0, 100.0),
        config=_config(),
        phase=GuidancePhase.MIDCOURSE,
    )

    assert command.phase == GuidancePhase.MIDCOURSE
    assert abs(command.lateral_accel_mps2) <= 30.0
    assert abs(command.vertical_accel_mps2) <= 20.0


def test_lead_pursuit_accounts_for_target_motion() -> None:
    command = LeadPursuit().compute(
        geometry=_geometry(),
        interceptor_pos=(0.0, 0.0, 0.0),
        target_pos=(500.0, 100.0, 0.0),
        target_vel=(0.0, 80.0, 0.0),
        config=_config(),
        phase=GuidancePhase.TERMINAL,
    )

    assert command.phase == GuidancePhase.TERMINAL
    assert command.heading_rate_rad_s > 0.0


def test_proportional_navigation_respects_lateral_limit() -> None:
    command = ProportionalNavigation().compute(
        geometry=_geometry(los_rate=2.0, closing_speed=500.0),
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(250.0, 0.0, 0.0),
        target_pos=(900.0, 200.0, 30.0),
        target_vel=(150.0, -40.0, 10.0),
        config=_config(),
        phase=GuidancePhase.TERMINAL,
    )

    assert abs(command.lateral_accel_mps2) == 30.0
