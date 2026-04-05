"""Unit tests for HMMWV M1151 A1 UGV platform adapter behavior."""

from __future__ import annotations

import time

from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter


def _force_dt(adapter: HMMWVAdapter, dt_s: float = 0.4) -> None:
    adapter._last_update_monotonic = time.monotonic() - dt_s  # noqa: SLF001


def test_connect_and_read_state_exposes_core_fields() -> None:
    adapter = HMMWVAdapter(seed=7)
    assert adapter.connect() is True

    state = adapter.read_state()
    assert state["connected"] is True
    assert state["vehicle_id"] == "HMMWV-M1151A1"
    assert "pose" in state
    assert "kinematics" in state
    assert "powertrain" in state
    assert "autonomy" in state
    assert "sensors" in state
    assert len(state["sensors"]["sensor_health"]) == 8


def test_physics_simulation_accelerates_and_consumes_fuel() -> None:
    adapter = HMMWVAdapter(seed=11)
    adapter.connect()
    baseline_fuel = adapter.read_state()["powertrain"]["fuel_l"]

    for _ in range(8):
        _force_dt(adapter, 0.5)
        adapter.apply_mobility_command({"throttle": 0.8, "brake": 0.0, "steering": 0.1})
        _force_dt(adapter, 0.5)
        state = adapter.read_state()

    assert state["kinematics"]["speed_mps"] > 1.0
    assert state["powertrain"]["fuel_l"] < baseline_fuel


def test_gps_denial_switches_to_gps_denied_navigation() -> None:
    adapter = HMMWVAdapter(seed=5)
    adapter.connect()
    adapter.simulate_gps_denial(enabled=True, duration_s=120.0)

    for _ in range(4):
        _force_dt(adapter, 0.6)
        adapter.read_state()

    denied_state = adapter.read_state()
    assert denied_state["navigation"]["gps_available"] is False
    assert denied_state["sensors"]["navigation"]["gps_x_m"] is None
    assert denied_state["navigation"]["odometry_drift_m"] > 0.0


def test_comms_loss_forces_degraded_mode_and_command_limits() -> None:
    adapter = HMMWVAdapter(seed=3)
    adapter.connect()
    adapter.set_autonomy_level(4)

    comms = adapter.simulate_comms_loss(duration_s=60.0)
    assert comms["comms_lost"] is True

    ack = adapter.apply_mobility_command({"throttle": 1.0, "brake": 0.0, "steering": 0.2})
    assert ack["accepted"] is True
    assert ack["commanded"]["throttle"] == 0.0
    assert ack["commanded"]["brake"] >= 0.5

    level = adapter.set_autonomy_level(4)
    assert level["autonomy_level"] <= 1
    assert level["degraded_mode"] is True


def test_sensor_dropout_triggers_degraded_mode_fallback() -> None:
    adapter = HMMWVAdapter(seed=19)
    adapter.connect()

    for sensor_name in ("camera_day", "camera_thermal", "lidar_front", "radar_front"):
        adapter.apply_sensor_command({"sensor": sensor_name, "enabled": False})

    state = adapter.read_state()
    assert state["autonomy"]["degraded_mode"] is True
    assert state["autonomy"]["degraded_reason"] == "sensor_dropout"

    level = adapter.set_autonomy_level(4)
    assert level["autonomy_level"] <= 2


def test_safe_state_applies_full_brake_and_manual_fallback() -> None:
    adapter = HMMWVAdapter(seed=29)
    adapter.connect()
    adapter.set_autonomy_level(3)
    safe = adapter.safe_state(reason="operator_override")

    assert safe["safe_state"] is True
    assert safe["controls"]["throttle"] == 0.0
    assert safe["controls"]["brake"] == 1.0
    assert safe["autonomy_level"] == 0


def test_navigation_stack_can_be_disabled_for_standalone_fallback() -> None:
    adapter = HMMWVAdapter(seed=41, use_navigation_modules=False)
    adapter.connect()
    state = adapter.read_state()

    assert state["navigation"]["backend"] == "fallback_physics"
    assert state["navigation"]["localization_mode"] in {"gps_fused", "dead_reckoning"}


def test_gps_denial_forces_dead_reckoning_in_navigation_stack() -> None:
    adapter = HMMWVAdapter(seed=43)
    adapter.connect()
    if not adapter.navigation_modules_available:
        return

    adapter.simulate_gps_denial(enabled=True, duration_s=45.0)
    for _ in range(3):
        _force_dt(adapter, 0.5)
        adapter.read_state()
    state = adapter.read_state()

    assert state["navigation"]["gps_available"] is False
    assert state["navigation"]["localization_mode"] == "dead_reckoning"
    assert state["sensors"]["navigation"]["gps_x_m"] is None


def test_degraded_mode_updates_operating_policy_budget() -> None:
    adapter = HMMWVAdapter(seed=47)
    adapter.connect()
    adapter.simulate_comms_loss(duration_s=90.0)
    state = adapter.read_state()
    budget = state["autonomy"]["compute_budget"]

    assert state["autonomy"]["degraded_mode"] is True
    assert "max_concurrent_models" in budget
    assert "max_autonomy_level" in budget
    capped = adapter.set_autonomy_level(4)
    assert capped["autonomy_level"] <= budget["max_autonomy_level"]
