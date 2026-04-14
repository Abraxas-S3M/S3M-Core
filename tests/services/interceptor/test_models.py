"""Unit tests for interceptor guidance models.

Military context:
Validation guards in these models prevent malformed fire-control data from
propagating into live engagement loops.
"""

from __future__ import annotations

import math

import pytest

from services.interceptor.models import (
    GuidancePhase,
    HandoffConfig,
    InterceptGeometry,
    InterceptorConfig,
    SteeringCommand,
)


def test_interceptor_config_requires_positive_guidance_rate() -> None:
    with pytest.raises(ValueError):
        InterceptorConfig(interceptor_id="i-1", guidance_update_hz=0.0)


def test_handoff_config_requires_valid_range_band() -> None:
    with pytest.raises(ValueError):
        HandoffConfig(min_handoff_range_m=400.0, max_handoff_range_m=300.0)


def test_intercept_geometry_rejects_invalid_vector() -> None:
    with pytest.raises(ValueError):
        InterceptGeometry(
            timestamp_s=0.1,
            range_m=100.0,
            closing_speed_mps=30.0,
            line_of_sight_unit=(1.0, 0.0),  # type: ignore[arg-type]
            line_of_sight_rate_rad_s=0.02,
            predicted_time_to_go_s=4.0,
            predicted_miss_distance_m=10.0,
            interceptor_speed_mps=250.0,
            target_speed_mps=150.0,
        )


def test_steering_command_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError):
        SteeringCommand(
            phase=GuidancePhase.MIDCOURSE,
            lateral_accel_mps2=math.nan,
        )
