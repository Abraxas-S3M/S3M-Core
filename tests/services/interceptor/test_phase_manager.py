"""Unit tests for interceptor phase-state transitions.

Military context:
State-machine correctness ensures command handoff and engagement disposition
remain deterministic under radar update pressure.
"""

from __future__ import annotations

from services.interceptor.models import GuidancePhase, HandoffConfig, InterceptGeometry, InterceptorState
from services.interceptor.phase_manager import GuidancePhaseManager


def _geometry(range_m: float, closing_speed: float) -> InterceptGeometry:
    return InterceptGeometry(
        timestamp_s=0.1,
        range_m=range_m,
        closing_speed_mps=closing_speed,
        line_of_sight_unit=(1.0, 0.0, 0.0),
        line_of_sight_rate_rad_s=0.02,
        predicted_time_to_go_s=5.0,
        predicted_miss_distance_m=20.0,
        interceptor_speed_mps=200.0,
        target_speed_mps=100.0,
    )


def test_phase_manager_progresses_to_autonomous_then_engaged() -> None:
    manager = GuidancePhaseManager(HandoffConfig())
    manager.launch()
    manager.radar_acquired()

    assert manager.phase == GuidancePhase.MIDCOURSE
    assert manager.state == InterceptorState.GUIDING
    assert manager.is_guided

    manager.update(_geometry(range_m=900.0, closing_speed=150.0))
    assert manager.phase == GuidancePhase.TERMINAL
    assert manager.is_guided

    manager.update(_geometry(range_m=250.0, closing_speed=120.0))
    assert manager.phase == GuidancePhase.AUTONOMOUS
    assert not manager.is_guided

    final_state = manager.update(_geometry(range_m=10.0, closing_speed=90.0))
    assert final_state == InterceptorState.ENGAGED
    assert manager.phase == GuidancePhase.POST_ENGAGE
    assert manager.is_complete


def test_phase_manager_marks_miss_for_opening_geometry() -> None:
    manager = GuidancePhaseManager(HandoffConfig())
    manager.launch()
    manager.radar_acquired()

    state = manager.update(_geometry(range_m=3_000.0, closing_speed=-20.0))
    assert state == InterceptorState.MISS
    assert manager.phase == GuidancePhase.POST_ENGAGE
    assert "opening range" in manager.abort_reason
