from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.maintenance.models import Asset, AssetCondition, AssetStatus, AssetType, SensorTelemetry
from services.maintenance.predictive import ConditionMonitor


def _asset() -> Asset:
    return Asset(
        asset_id="ast-1",
        name="Engine",
        designation="F-15SA #201",
        asset_type=AssetType.FIGHTER_JET,
        status=AssetStatus.OPERATIONAL,
        condition=AssetCondition.GOOD,
        serial_number="SN-1",
        manufacturer="S3M",
        model="X",
        acquisition_date=datetime.now(timezone.utc) - timedelta(days=300),
        operating_hours=2200.0,
        cycles=3200,
        location="Base",
        assigned_unit="Wing",
    )


def _telemetry(temp: float = 430.0, vib: float = 2.0) -> SensorTelemetry:
    return SensorTelemetry(
        asset_id="ast-1",
        timestamp=datetime.now(timezone.utc),
        readings={
            "temperature_c": temp,
            "vibration_g": vib,
            "pressure_psi": 35.0,
            "oil_temp_c": 90.0,
            "rpm_deviation_pct": 1.0,
        },
        operating_mode="cruise",
    )


def test_evaluate_temperature_warning():
    mon = ConditionMonitor()
    res = mon.evaluate(_telemetry(temp=500.0))
    assert res["condition"] == AssetCondition.FAIR
    assert any(a["sensor"] == "temperature_c" for a in res["alerts"])


def test_evaluate_vibration_critical():
    mon = ConditionMonitor()
    res = mon.evaluate(_telemetry(vib=6.0))
    assert res["condition"] == AssetCondition.CRITICAL
    assert any(a["severity"] == "critical" for a in res["alerts"])


def test_evaluate_all_normal():
    mon = ConditionMonitor()
    res = mon.evaluate(_telemetry(temp=420.0, vib=2.2))
    assert res["condition"] == AssetCondition.GOOD
    assert res["alerts"] == []


def test_evaluate_trend_detects_degrading_temperature():
    mon = ConditionMonitor()
    now = datetime.now(timezone.utc)
    history = []
    for i in range(12):
        history.append(
            SensorTelemetry(
                asset_id="ast-1",
                timestamp=now - timedelta(minutes=10 * (12 - i)),
                readings={"temperature_c": 410 + i * 8, "vibration_g": 2.0, "pressure_psi": 35.0},
                operating_mode="cruise",
            )
        )
    trend = mon.evaluate_trend(history, window=10)
    assert "temperature_c" in trend["degrading_sensors"]


def test_generate_condition_report_non_empty():
    mon = ConditionMonitor()
    asset = _asset()
    report = mon.generate_condition_report(asset, [_telemetry(), _telemetry(temp=450.0)])
    assert isinstance(report, str)
    assert report.strip()
