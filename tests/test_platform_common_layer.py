from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.platforms.common import (
    CAPABILITY_REGISTRY,
    AuthorityLevel,
    AuthorizationType,
    FaultSeverity,
    HealthMonitor,
    HealthState,
    OperatorAuthorization,
    PlatformState,
    PlatformType,
    Track,
    get_capabilities,
)


def test_get_capabilities_returns_defensive_copy() -> None:
    cap = get_capabilities("hmmwv_m1151")
    assert cap.platform_type == PlatformType.UGV

    cap.sensor_types.append("spoofed_sensor")
    fresh = get_capabilities("hmmwv_m1151")
    assert "spoofed_sensor" not in fresh.sensor_types


def test_get_capabilities_validates_key() -> None:
    with pytest.raises(ValueError):
        get_capabilities("")
    with pytest.raises(KeyError):
        get_capabilities("unknown_platform")
    assert "warwar_uas" in CAPABILITY_REGISTRY


def test_track_confidence_is_clamped() -> None:
    assert Track(track_id="a", confidence=9.9).confidence == 1.0
    assert Track(track_id="b", confidence=-1.0).confidence == 0.0


def test_operator_authorization_expiration() -> None:
    expired = OperatorAuthorization(
        operator_id="op-1",
        auth_type=AuthorizationType.OVERRIDE,
        authority_level=AuthorityLevel.MISSION_COMMANDER,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    assert expired.is_expired is True


def test_health_monitor_detects_critical_faults() -> None:
    monitor = HealthMonitor()
    state = PlatformState(
        platform_id="alpha-1",
        platform_type=PlatformType.UGV,
        health=HealthState(
            cpu_temp_c=91.0,
            gpu_temp_c=93.0,
            memory_pct=96.0,
            disk_pct=98.0,
            power_voltage=19.0,
        ),
        fuel_pct=8.0,
        battery_pct=10.0,
        comms_status="lost",
    )

    faults = monitor.detect_faults(state)
    assert any(f.source == "cpu" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "gpu" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "memory" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "disk" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "power" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "fuel" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "battery" and f.severity == FaultSeverity.CRITICAL for f in faults)
    assert any(f.source == "comms" and f.severity == FaultSeverity.CRITICAL for f in faults)


def test_health_monitor_platform_override_thresholds() -> None:
    monitor = HealthMonitor()
    monitor.register_platform("tower-1", {"cpu_temp_warn_c": 50.0, "cpu_temp_critical_c": 60.0})

    state = PlatformState(
        platform_id="tower-1",
        platform_type=PlatformType.FIXED_NODE,
        health=HealthState(cpu_temp_c=61.0),
    )
    faults = monitor.detect_faults(state)
    assert any(f.source == "cpu" and f.severity == FaultSeverity.CRITICAL for f in faults)

    checked = monitor.check_health(state)
    assert checked.has_critical_faults is True
