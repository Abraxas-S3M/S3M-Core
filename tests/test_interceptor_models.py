"""Unit tests for interceptor guidance data models.

Military context:
These checks ensure serialized guidance outputs remain stable for interceptor
handoff logic, enabling reliable tactical telemetry and after-action replay.
"""

from datetime import datetime, timezone

from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    GuidanceSolution,
    InterceptGeometry,
    InterceptorConfig,
    InterceptorState,
    SteeringCommand,
)


def test_intercept_geometry_to_dict_rounds_float_fields() -> None:
    geometry = InterceptGeometry(
        range_m=1450.6789,
        closing_velocity_mps=72.3499,
        time_to_intercept_s=19.4444,
        line_of_sight_az_deg=11.1239,
        line_of_sight_el_deg=-2.9876,
        los_rate_az_dps=0.33339,
        los_rate_el_dps=-0.12666,
        lead_angle_deg=4.77776,
        predicted_miss_distance_m=12.3499,
        aspect_angle_deg=25.0199,
        crossing_angle_deg=41.6789,
    )

    payload = geometry.to_dict()
    assert payload["range_m"] == 1450.679
    assert payload["los_rate_az_dps"] == 0.333
    assert payload["predicted_miss_distance_m"] == 12.35


def test_steering_command_to_dict_serializes_all_fields() -> None:
    command = SteeringCommand(
        timestamp=datetime(2026, 4, 14, 10, 30, tzinfo=timezone.utc),
        commanded_heading_deg=182.449,
        commanded_pitch_deg=-3.876,
        commanded_speed_mps=67.889,
        commanded_position=(1000.0, 2000.0, 320.0),
        lateral_accel_mps2=5.5555,
        vertical_accel_mps2=-1.2345,
        guidance_mode=GuidanceMode.AUGMENTED_PN,
        phase=GuidancePhase.TERMINAL,
    )

    payload = command.to_dict()
    assert payload["timestamp"] == "2026-04-14T10:30:00+00:00"
    assert payload["heading_deg"] == 182.45
    assert payload["pitch_deg"] == -3.88
    assert payload["speed_mps"] == 67.89
    assert payload["position"] == [1000.0, 2000.0, 320.0]
    assert payload["lat_accel"] == 5.556
    assert payload["vert_accel"] == -1.234
    assert payload["mode"] == "augmented_pn"
    assert payload["phase"] == "terminal"


def test_interceptor_config_to_dict_uses_handoff_nested_field() -> None:
    config = InterceptorConfig(
        interceptor_id="intc-alpha",
        name_en="Titan",
        max_speed_mps=95.0,
    )
    config.handoff.handoff_range_m = 275.0

    payload = config.to_dict()
    assert payload["interceptor_id"] == "intc-alpha"
    assert payload["name_en"] == "Titan"
    assert payload["max_speed_mps"] == 95.0
    assert payload["handoff_range_m"] == 275.0
    assert payload["kill_radius_m"] == 5.0


def test_guidance_solution_to_dict_embeds_geometry_and_command() -> None:
    solution = GuidanceSolution(
        solution_id="gsol-1",
        interceptor_id="intc-1",
        target_id="tgt-9",
        cycle_number=7,
        geometry=InterceptGeometry(range_m=321.5555),
        command=SteeringCommand(commanded_heading_deg=45.987),
        phase=GuidancePhase.AUTONOMOUS,
        state=InterceptorState.AUTONOMOUS_HANDOFF,
        feasible=False,
        abort_reason="seeker_lost_lock",
    )

    payload = solution.to_dict()
    assert payload["solution_id"] == "gsol-1"
    assert payload["interceptor_id"] == "intc-1"
    assert payload["target_id"] == "tgt-9"
    assert payload["cycle"] == 7
    assert payload["geometry"]["range_m"] == 321.555
    assert payload["command"]["heading_deg"] == 45.99
    assert payload["phase"] == "autonomous"
    assert payload["state"] == "autonomous_handoff"
    assert payload["feasible"] is False
    assert payload["abort_reason"] == "seeker_lost_lock"
