"""Unit tests for safety and governance shell control authority services."""

from __future__ import annotations

import pytest

from src.safety.control_authority import (
    AuthorityLevel,
    ControlAuthorityService,
    InterlockState,
    InterlockStateMachine,
    RangeComplianceEngine,
    SimMode,
    SimModeGuard,
)


def _bootstrap_authority() -> tuple[ControlAuthorityService, dict[str, str]]:
    service = ControlAuthorityService(token_ttl_seconds=3600)
    service.register_operator("obs-1", "Observer One", AuthorityLevel.OBSERVER)
    service.register_operator("op-1", "Operator One", AuthorityLevel.OPERATOR)
    service.register_operator("wo-1", "Weapons Officer One", AuthorityLevel.WEAPONS_OFFICER)
    service.register_operator("mc-1", "Mission Commander One", AuthorityLevel.MISSION_COMMANDER)
    tokens = {
        "observer": service.issue_token("obs-1"),
        "operator": service.issue_token("op-1"),
        "weapons_officer": service.issue_token("wo-1"),
        "mission_commander": service.issue_token("mc-1"),
    }
    return service, tokens


def test_control_authority_hierarchy_validation():
    service, tokens = _bootstrap_authority()
    assert service.validate_token(tokens["observer"], AuthorityLevel.OBSERVER)
    assert not service.validate_token(tokens["observer"], AuthorityLevel.OPERATOR)
    assert service.validate_token(tokens["mission_commander"], AuthorityLevel.WEAPONS_OFFICER)
    assert service.has_authority("wo-1", AuthorityLevel.OPERATOR)
    assert not service.has_authority("op-1", AuthorityLevel.MISSION_COMMANDER)


def test_control_authority_token_revocation_blocks_access():
    service, tokens = _bootstrap_authority()
    service.revoke_token(tokens["operator"], reason="credential_compromise")
    with pytest.raises(PermissionError):
        service.assert_authorized(tokens["operator"], AuthorityLevel.OBSERVER)


def test_interlock_state_transitions_are_authorization_gated():
    service, tokens = _bootstrap_authority()
    interlock = InterlockStateMachine(service)
    with pytest.raises(PermissionError):
        interlock.transition_to(InterlockState.ARMED, tokens["operator"])

    interlock.transition_to(InterlockState.ARMED, tokens["weapons_officer"], reason="preflight")
    assert interlock.state == InterlockState.ARMED

    with pytest.raises(PermissionError):
        interlock.transition_to(InterlockState.FIRING, tokens["weapons_officer"])

    interlock.transition_to(InterlockState.FIRING, tokens["mission_commander"], reason="engage")
    assert interlock.state == InterlockState.FIRING
    assert interlock.can_actuate() is True


def test_interlock_fault_and_emergency_stop_latch_behavior():
    service, tokens = _bootstrap_authority()
    interlock = InterlockStateMachine(service)
    interlock.transition_to(InterlockState.ARMED, tokens["weapons_officer"])
    interlock.report_fault(tokens["operator"], fault_code="BUS_TIMEOUT", description="fire bus timeout")
    assert interlock.state == InterlockState.SAFE
    assert interlock.fault is not None

    with pytest.raises(PermissionError):
        interlock.transition_to(InterlockState.FIRING, tokens["mission_commander"])

    interlock.clear_fault(tokens["mission_commander"])
    interlock.transition_to(InterlockState.ARMED, tokens["weapons_officer"])
    interlock.emergency_stop(tokens["operator"], reason="range_ceasefire")
    assert interlock.state == InterlockState.SAFE
    assert interlock.emergency_stop_latched is True

    with pytest.raises(PermissionError):
        interlock.transition_to(InterlockState.ARMED, tokens["weapons_officer"])

    interlock.reset_emergency_stop(tokens["mission_commander"])
    interlock.transition_to(InterlockState.ARMED, tokens["weapons_officer"])
    assert interlock.state == InterlockState.ARMED


def test_sim_mode_guard_allows_only_mission_commander_to_switch_modes():
    service, tokens = _bootstrap_authority()
    guard = SimModeGuard(service)
    assert guard.mode == SimMode.SIMULATION

    with pytest.raises(PermissionError):
        guard.switch_mode(tokens["weapons_officer"], SimMode.LIVE)

    guard.switch_mode(tokens["mission_commander"], SimMode.LIVE, reason="live_range_window")
    assert guard.mode == SimMode.LIVE
    guard.assert_command_mode(simulated_command=False)

    with pytest.raises(PermissionError):
        guard.assert_command_mode(simulated_command=True)


def test_range_compliance_engine_enforces_limits_and_geofences():
    engine = RangeComplianceEngine(min_altitude_m=10.0, max_altitude_m=150.0, max_speed_mps=60.0)
    engine.add_allowed_zone(
        "range_alpha",
        [(10.0, 10.0), (10.0, 20.0), (20.0, 20.0), (20.0, 10.0)],
    )
    engine.add_restricted_zone(
        "no_fire_block",
        [(14.0, 14.0), (14.0, 16.0), (16.0, 16.0), (16.0, 14.0)],
    )

    compliant = engine.evaluate(latitude=12.0, longitude=12.0, altitude_m=60.0, speed_mps=20.0)
    assert compliant.compliant is True
    assert compliant.violations == ()

    boundary = engine.evaluate(latitude=10.0, longitude=15.0, altitude_m=60.0, speed_mps=20.0)
    assert boundary.compliant is True

    non_compliant = engine.evaluate(latitude=15.0, longitude=15.0, altitude_m=170.0, speed_mps=75.0)
    assert non_compliant.compliant is False
    codes = {violation.code for violation in non_compliant.violations}
    assert "RESTRICTED_ZONE" in codes
    assert "ALTITUDE_LIMIT" in codes
    assert "SPEED_LIMIT" in codes
    assert engine.get_violation_log()


def test_range_compliance_engine_can_evaluate_mapping_message_payload():
    engine = RangeComplianceEngine(min_altitude_m=5.0, max_altitude_m=100.0, max_speed_mps=30.0)
    engine.add_allowed_zone(
        "range_bravo",
        [(0.0, 0.0), (0.0, 5.0), (5.0, 5.0), (5.0, 0.0)],
    )
    report = engine.evaluate_message(
        {
            "latitude": 1.0,
            "longitude": 1.0,
            "altitude_m": 30.0,
            "speed_mps": 10.0,
        }
    )
    assert report.compliant is True
