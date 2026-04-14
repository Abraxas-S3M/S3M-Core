from __future__ import annotations

from services.interceptor.autopilot_adapter import AutopilotAdapter
from services.interceptor.geometry import compute_intercept_geometry
from services.interceptor.guidance_computer import InterceptorGuidanceComputer
from services.interceptor.guidance_laws import (
    lead_pursuit_command,
    proportional_navigation_command,
    pure_pursuit_command,
)
from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import GuidanceMode, GuidancePhase, InterceptorConfig
from services.interceptor.phase_manager import GuidancePhaseManager


def _build_config() -> InterceptorConfig:
    return InterceptorConfig(
        interceptor_type="test_interceptor",
        name_en="Test Interceptor",
        name_ar="معترض اختبار",
        max_speed_mps=70.0,
        max_acceleration_mps2=12.0,
        update_rate_hz=20.0,
        terminal_approach_range_m=1000.0,
    )


def test_geometry_computes_closing_and_time_to_intercept() -> None:
    geometry = compute_intercept_geometry(
        interceptor_position_m=(0.0, 0.0, 0.0),
        interceptor_velocity_mps=(20.0, 0.0, 0.0),
        target_position_m=(1000.0, 0.0, 0.0),
        target_velocity_mps=(0.0, 0.0, 0.0),
        interceptor_max_speed_mps=70.0,
    )
    assert geometry.range_m == 1000.0
    assert geometry.closing_velocity_mps > 0.0
    assert geometry.predicted_miss_distance_m < 1e-6
    assert geometry.time_to_intercept_s is not None


def test_guidance_laws_generate_distinct_modes() -> None:
    config = _build_config()
    geometry = compute_intercept_geometry(
        interceptor_position_m=(0.0, 0.0, 0.0),
        interceptor_velocity_mps=(10.0, 0.0, 0.0),
        target_position_m=(800.0, 120.0, 50.0),
        target_velocity_mps=(-5.0, 8.0, 0.0),
        interceptor_max_speed_mps=config.max_speed_mps,
    )
    pure = pure_pursuit_command((10.0, 0.0, 0.0), geometry, config, dt_s=0.05)
    lead = lead_pursuit_command((10.0, 0.0, 0.0), (-5.0, 8.0, 0.0), geometry, config, dt_s=0.05)
    pn = proportional_navigation_command((10.0, 0.0, 0.0), geometry, config, dt_s=0.05)

    assert pure.mode == GuidanceMode.PURE_PURSUIT
    assert lead.mode == GuidanceMode.LEAD_PURSUIT
    assert pn.mode == GuidanceMode.PROPORTIONAL_NAVIGATION
    assert 0.0 <= pn.throttle_fraction <= 1.0


def test_phase_manager_transitions_to_handoff_window() -> None:
    config = _build_config()
    manager = GuidancePhaseManager(config=config)
    manager.advance(3000.0, launched=True, radar_acquired=False, autonomous_handoff_confirmed=False, engaged=False, abort_recommended=False)
    manager.advance(1500.0, launched=True, radar_acquired=True, autonomous_handoff_confirmed=False, engaged=False, abort_recommended=False)
    state, phase, _ = manager.advance(
        250.0,
        launched=True,
        radar_acquired=True,
        autonomous_handoff_confirmed=False,
        engaged=False,
        abort_recommended=False,
    )
    assert state.value == "autonomous_handoff"
    assert phase == GuidancePhase.AUTONOMOUS_HANDOFF


def test_guidance_computer_recommends_handoff_in_window() -> None:
    computer = InterceptorGuidanceComputer(interceptor_id="intc-1", config=_build_config())
    computer.compute_solution(
        target_id="t-1",
        interceptor_position_m=(0.0, 0.0, 100.0),
        interceptor_velocity_mps=(30.0, 0.0, 0.0),
        target_position_m=(950.0, 0.0, 100.0),
        target_velocity_mps=(0.0, 0.0, 0.0),
        launched=True,
        radar_acquired=True,
    )
    solution = computer.compute_solution(
        target_id="t-1",
        interceptor_position_m=(0.0, 0.0, 100.0),
        interceptor_velocity_mps=(35.0, 0.0, 0.0),
        target_position_m=(250.0, 0.0, 100.0),
        target_velocity_mps=(0.0, 0.0, 0.0),
        launched=True,
        radar_acquired=True,
    )
    assert solution.handoff_recommended is True
    assert solution.phase == GuidancePhase.AUTONOMOUS_HANDOFF


def test_guidance_computer_marks_engaged_inside_terminal_range() -> None:
    computer = InterceptorGuidanceComputer(interceptor_id="intc-2", config=_build_config())
    solution = computer.compute_solution(
        target_id="t-close",
        interceptor_position_m=(0.0, 0.0, 100.0),
        interceptor_velocity_mps=(5.0, 0.0, 0.0),
        target_position_m=(5.0, 0.0, 100.0),
        target_velocity_mps=(0.0, 0.0, 0.0),
        launched=True,
        radar_acquired=True,
    )
    assert solution.phase == GuidancePhase.ENGAGED


def test_autopilot_adapter_translates_solution_to_move_to() -> None:
    config = _build_config()
    computer = InterceptorGuidanceComputer(interceptor_id="intc-3", config=config)
    solution = computer.compute_solution(
        target_id="t-2",
        interceptor_position_m=(0.0, 0.0, 50.0),
        interceptor_velocity_mps=(15.0, 0.0, 0.0),
        target_position_m=(600.0, 40.0, 70.0),
        target_velocity_mps=(-4.0, 0.0, 0.0),
        launched=True,
        radar_acquired=True,
    )
    adapter = AutopilotAdapter(command_horizon_s=1.0)
    command = adapter.solution_to_command((0.0, 0.0, 50.0), solution)
    assert command["type"] in {"MOVE_TO", "HOLD"}
    if command["type"] == "MOVE_TO":
        assert len(command["position"]) == 3


def test_interceptor_manager_register_launch_assign_guide() -> None:
    manager = InterceptorManager()
    config = _build_config()
    manager.register_interceptor(interceptor_id="fleet-1", config=config)
    manager.launch_interceptor("fleet-1", takeoff_altitude_m=120.0)
    manager.assign_target(
        interceptor_id="fleet-1",
        target_id="trk-1",
        target_position_m=(1800.0, 200.0, 300.0),
        target_velocity_mps=(-20.0, 0.0, 0.0),
        request_allocation=False,
    )
    solution = manager.guide_interceptor("fleet-1", dt_s=0.2)
    assert solution.target_id == "trk-1"
    assert solution.geometry.range_m > 0.0
