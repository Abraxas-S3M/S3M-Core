"""Unit tests for interceptor guidance phase transitions.

Military context:
These tests validate deterministic launch-to-engagement state movement and
abort gates that protect tactical air-defense shots from unsafe geometry.
"""

import pytest

from services.interceptor.models import GuidancePhase, HandoffCriteria, InterceptGeometry, InterceptorState
from services.interceptor.phase_manager import GuidancePhaseManager


def _geometry(range_m: float, closing_mps: float = 300.0, miss_m: float = 5.0) -> InterceptGeometry:
    return InterceptGeometry(
        range_m=range_m,
        closing_velocity_mps=closing_mps,
        predicted_miss_distance_m=miss_m,
    )


def test_handoff_criteria_rejects_invalid_ranges():
    with pytest.raises(ValueError):
        HandoffCriteria(terminal_range_m=200.0, handoff_range_m=200.0)

    with pytest.raises(ValueError):
        HandoffCriteria(max_miss_distance_m=0.0)


def test_intercept_geometry_rejects_non_finite_or_negative_values():
    with pytest.raises(ValueError):
        InterceptGeometry(range_m=-1.0, closing_velocity_mps=1.0, predicted_miss_distance_m=1.0)

    with pytest.raises(ValueError):
        InterceptGeometry(range_m=10.0, closing_velocity_mps=float("nan"), predicted_miss_distance_m=1.0)


def test_manager_transitions_from_launch_to_engaged():
    manager = GuidancePhaseManager()
    manager.launch()
    manager.radar_acquired()

    assert manager.update(_geometry(1200.0)) == InterceptorState.MIDCOURSE_GUIDED
    assert manager.phase == GuidancePhase.MIDCOURSE
    assert manager.is_guided is True

    assert manager.update(_geometry(450.0)) == InterceptorState.TERMINAL_APPROACH
    assert manager.phase == GuidancePhase.TERMINAL

    assert manager.update(_geometry(200.0)) == InterceptorState.AUTONOMOUS_HANDOFF
    assert manager.phase == GuidancePhase.AUTONOMOUS
    assert manager.is_terminal is True

    assert manager.update(_geometry(9.0)) == InterceptorState.ENGAGED
    assert manager.phase == GuidancePhase.POST_ENGAGE
    assert manager.is_complete is True


def test_manager_aborts_when_closing_velocity_too_low_in_midcourse():
    manager = GuidancePhaseManager()
    manager.launch()
    manager.radar_acquired()
    manager.update(_geometry(1200.0))

    state = manager.update(
        InterceptGeometry(
            range_m=800.0,
            closing_velocity_mps=manager.handoff.min_closing_velocity_mps - 1.0,
            predicted_miss_distance_m=3.0,
        )
    )

    assert state == InterceptorState.MISS
    assert manager.phase == GuidancePhase.POST_ENGAGE
    assert "Closing velocity" in manager.abort_reason
    assert manager.is_complete is True


def test_manager_aborts_when_predicted_miss_exceeds_limit_near_terminal():
    manager = GuidancePhaseManager()
    manager.launch()
    manager.radar_acquired()
    manager.update(_geometry(1200.0))

    state = manager.update(
        InterceptGeometry(
            range_m=600.0,
            closing_velocity_mps=manager.handoff.min_closing_velocity_mps + 30.0,
            predicted_miss_distance_m=manager.handoff.max_miss_distance_m + 2.0,
        )
    )

    assert state == InterceptorState.MISS
    assert "Predicted miss" in manager.abort_reason


def test_update_requires_intercept_geometry_instance():
    manager = GuidancePhaseManager()
    manager.launch()
    manager.radar_acquired()

    with pytest.raises(TypeError):
        manager.update({"range_m": 1000.0})  # type: ignore[arg-type]


def test_reset_clears_abort_and_restarts_sequence():
    manager = GuidancePhaseManager()
    manager.launch()
    manager.radar_acquired()
    manager.update(_geometry(1200.0))
    manager.update(
        InterceptGeometry(
            range_m=800.0,
            closing_velocity_mps=manager.handoff.min_closing_velocity_mps - 2.0,
            predicted_miss_distance_m=1.0,
        )
    )
    assert manager.state == InterceptorState.MISS
    assert manager.abort_reason

    manager.reset()
    assert manager.state == InterceptorState.PRELAUNCH
    assert manager.phase == GuidancePhase.BOOST
    assert manager.abort_reason == ""
