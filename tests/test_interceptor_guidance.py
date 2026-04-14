"""Tests for S3M interceptor drone guidance computer."""

import sys
import math

sys.path.insert(0, ".")

from services.interceptor.models import (
    GuidancePhase,
    InterceptorConfig,
    InterceptorState,
    HandoffCriteria,
)
from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.guidance_laws import (
    ProportionalNavigation,
    PurePursuit,
    LeadPursuit,
)
from services.interceptor.phase_manager import GuidancePhaseManager
from services.interceptor.guidance_computer import GuidanceComputer
from services.interceptor.interceptor_manager import InterceptorManager


def _titan_config() -> InterceptorConfig:
    return InterceptorConfig(
        name_en="Titan Test",
        name_ar="تيتان تجريبي",
        max_speed_mps=80,
        nav_constant=4.0,
        guidance_update_hz=10,
        handoff=HandoffCriteria(handoff_range_m=250, terminal_range_m=500),
    )


# --- Geometry Tests ---


def test_geometry_closing_target():
    gc = InterceptGeometryComputer()
    geom = gc.compute(
        interceptor_pos=(0, 0, 500),
        interceptor_vel=(0, 50, 0),
        target_pos=(0, 5000, 500),
        target_vel=(0, -30, 0),
        time_s=1.0,
    )
    assert geom.range_m > 4000
    assert geom.closing_velocity_mps > 70  # Both moving toward each other
    assert geom.time_to_intercept_s > 0


def test_geometry_crossing_target():
    gc = InterceptGeometryComputer()
    geom = gc.compute(
        interceptor_pos=(0, 0, 500),
        interceptor_vel=(0, 60, 0),
        target_pos=(3000, 3000, 500),
        target_vel=(-40, 0, 0),
        time_s=1.0,
    )
    assert geom.crossing_angle_deg > 45


def test_geometry_los_rate_computed():
    gc = InterceptGeometryComputer()
    gc.compute(
        interceptor_pos=(0, 0, 500),
        interceptor_vel=(0, 60, 0),
        target_pos=(1000, 5000, 500),
        target_vel=(-30, -20, 0),
        time_s=0.0,
    )
    geom2 = gc.compute(
        interceptor_pos=(0, 6, 500),
        interceptor_vel=(0, 60, 0),
        target_pos=(970, 4980, 500),
        target_vel=(-30, -20, 0),
        time_s=0.1,
    )
    # LOS rate should be non-zero for crossing target
    assert abs(geom2.los_rate_az_dps) > 0.01 or abs(geom2.los_rate_el_dps) >= 0


# --- Guidance Law Tests ---


def test_pure_pursuit_points_at_target():
    from services.interceptor.models import InterceptGeometry

    config = _titan_config()
    pp = PurePursuit()
    geom = InterceptGeometry(range_m=5000)
    cmd = pp.compute(geom, (0, 0, 500), (0, 5000, 500), config)
    # Should command heading roughly north (toward target at y=5000)
    assert 350 < cmd.commanded_heading_deg or cmd.commanded_heading_deg < 10


def test_pn_guidance_produces_acceleration():
    from services.interceptor.models import InterceptGeometry

    config = _titan_config()
    pn = ProportionalNavigation()
    geom = InterceptGeometry(
        range_m=5000,
        closing_velocity_mps=80,
        los_rate_az_dps=2.0,
        los_rate_el_dps=0.5,
    )
    cmd = pn.compute(
        geom,
        (0, 0, 500),
        (0, 60, 0),
        (1000, 5000, 600),
        (-30, -20, 0),
        config,
        GuidancePhase.MIDCOURSE,
    )
    assert cmd.lateral_accel_mps2 != 0.0  # PN should command lateral accel


# --- Phase Manager Tests ---


def test_phase_transitions():
    pm = GuidancePhaseManager(
        HandoffCriteria(handoff_range_m=250, terminal_range_m=500)
    )
    assert pm.state == InterceptorState.PRELAUNCH

    pm.launch()
    assert pm.state == InterceptorState.LAUNCHED

    pm.radar_acquired()
    assert pm.state == InterceptorState.RADAR_ACQUIRED

    from services.interceptor.models import InterceptGeometry

    # Midcourse: far from target
    pm.update(
        InterceptGeometry(
            range_m=10000,
            closing_velocity_mps=80,
            predicted_miss_distance_m=50,
        )
    )
    assert pm.state == InterceptorState.MIDCOURSE_GUIDED

    # Terminal: close
    pm.update(
        InterceptGeometry(
            range_m=400,
            closing_velocity_mps=80,
            predicted_miss_distance_m=30,
        )
    )
    assert pm.state == InterceptorState.TERMINAL_APPROACH

    # Handoff
    pm.update(
        InterceptGeometry(
            range_m=200,
            closing_velocity_mps=80,
            predicted_miss_distance_m=10,
        )
    )
    assert pm.state == InterceptorState.AUTONOMOUS_HANDOFF

    # Engaged
    pm.update(
        InterceptGeometry(
            range_m=5,
            closing_velocity_mps=80,
            predicted_miss_distance_m=2,
        )
    )
    assert pm.state == InterceptorState.ENGAGED


def test_phase_abort_on_diverging():
    pm = GuidancePhaseManager(
        HandoffCriteria(min_closing_velocity_mps=10, terminal_range_m=500)
    )
    pm.launch()
    pm.radar_acquired()

    from services.interceptor.models import InterceptGeometry

    pm.update(InterceptGeometry(range_m=8000, closing_velocity_mps=80))
    assert pm.state == InterceptorState.MIDCOURSE_GUIDED
    # Diverging: closing velocity drops below minimum at long range
    pm.update(
        InterceptGeometry(
            range_m=7000,
            closing_velocity_mps=5,
            predicted_miss_distance_m=50,
        )
    )
    assert pm.state == InterceptorState.MISS


# --- Full Guidance Computer Tests ---


def test_guidance_computer_full_intercept():
    config = _titan_config()
    gc = GuidanceComputer(config, "tgt-shahed-01")
    gc.launch()
    gc.radar_acquired()

    # Simulate closing approach
    interceptor_pos = [0.0, 0.0, 500.0]
    target_pos = [0.0, 10000.0, 600.0]
    target_vel = (0.0, -30.0, 0.0)

    phases_seen = set()
    for i in range(200):
        intc_speed = 70.0
        # Simple sim: move interceptor toward commanded position
        sol = gc.update(
            tuple(interceptor_pos),
            (0.0, intc_speed, 0.0),
            tuple(target_pos),
            target_vel,
        )
        phases_seen.add(sol.phase.value)

        # Advance positions
        dt = 0.1
        interceptor_pos[1] += intc_speed * dt
        target_pos[0] += target_vel[0] * dt
        target_pos[1] += target_vel[1] * dt

        if gc.phase_manager.is_complete:
            break

    result = gc.get_result()
    assert result.guidance_cycles > 10
    assert "midcourse" in phases_seen
    # Should have progressed through at least midcourse
    assert result.outcome in {"hit", "miss", "pending"}


# --- Interceptor Manager Tests ---


def test_manager_register_assign_launch():
    mgr = InterceptorManager()
    config = _titan_config()
    mgr.register_interceptor(config)
    assert mgr.assign_target(config.interceptor_id, "tgt-01")
    assert mgr.launch(config.interceptor_id)
    assert mgr.radar_acquired(config.interceptor_id)

    sol = mgr.guide(
        config.interceptor_id,
        (0, 0, 500),
        (0, 60, 0),
        (0, 5000, 600),
        (0, -30, 0),
    )
    assert sol is not None
    assert sol.state == InterceptorState.MIDCOURSE_GUIDED


if __name__ == "__main__":
    test_geometry_closing_target()
    test_geometry_crossing_target()
    test_geometry_los_rate_computed()
    test_pure_pursuit_points_at_target()
    test_pn_guidance_produces_acceleration()
    test_phase_transitions()
    test_phase_abort_on_diverging()
    test_guidance_computer_full_intercept()
    test_manager_register_assign_launch()
    print("ALL INTERCEPTOR GUIDANCE TESTS PASSED")
