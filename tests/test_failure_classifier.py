from __future__ import annotations

from datetime import datetime, timezone

from services.maintenance.models import AssetType, SensorTelemetry
from services.maintenance.predictive import FailureClassifier


def _telemetry(**kwargs) -> SensorTelemetry:
    base = {
        "temperature_c": 430.0,
        "vibration_g": 2.0,
        "pressure_psi": 36.0,
        "oil_temp_c": 95.0,
        "rpm_deviation_pct": 1.0,
    }
    base.update(kwargs)
    return SensorTelemetry(
        asset_id="ast-1",
        timestamp=datetime.now(timezone.utc),
        readings=base,
        operating_mode="cruise",
    )


def test_high_temp_high_vibration_bearing_degradation():
    clf = FailureClassifier()
    out = clf.classify(_telemetry(temperature_c=550.0, vibration_g=6.2), AssetType.FIGHTER_JET)
    assert out["failure_mode"] == "bearing_degradation"


def test_low_pressure_high_oil_temp_seal_leak():
    clf = FailureClassifier()
    out = clf.classify(_telemetry(pressure_psi=18.0, oil_temp_c=125.0), AssetType.TANK)
    assert out["failure_mode"] == "seal_leak"


def test_rpm_deviation_control_system_fault():
    clf = FailureClassifier()
    out = clf.classify(_telemetry(rpm_deviation_pct=12.0), AssetType.AIRCRAFT)
    assert out["failure_mode"] == "control_system_fault"


def test_all_normal_gradual_wear():
    clf = FailureClassifier()
    out = clf.classify(_telemetry(), AssetType.AIRCRAFT)
    assert out["failure_mode"] == "gradual_wear"
