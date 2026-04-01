from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetStatus,
    AssetType,
    SensorTelemetry,
)
from services.maintenance.predictive import RULEstimator


def _asset(hours: float = 1000.0) -> Asset:
    return Asset(
        asset_id="ast-1",
        name="Engine",
        designation="F-15SA #999",
        asset_type=AssetType.FIGHTER_JET,
        status=AssetStatus.OPERATIONAL,
        condition=AssetCondition.GOOD,
        serial_number="SN-001",
        manufacturer="S3M",
        model="E-1",
        acquisition_date=datetime.now(timezone.utc) - timedelta(days=400),
        operating_hours=hours,
        cycles=1200,
        location="Base",
        assigned_unit="Wing",
    )


def _history(temp: float, vib: float, pressure_start: float = 35.0, pressure_end: float = 34.5) -> list[SensorTelemetry]:
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(12):
        pressure = pressure_start + (pressure_end - pressure_start) * (i / 11.0)
        rows.append(
            SensorTelemetry(
                asset_id="ast-1",
                timestamp=now - timedelta(minutes=(12 - i)),
                readings={
                    "temperature_c": temp,
                    "vibration_g": vib,
                    "pressure_psi": pressure,
                    "oil_temp_c": 95.0,
                    "rpm": 12000.0,
                    "fuel_flow_rate": 0.82,
                },
                operating_mode="cruise",
            )
        )
    return rows


def test_rule_based_high_temperature_yields_critical():
    estimator = RULEstimator(model_backend="rules")
    prediction = estimator.predict(_history(temp=520.0, vib=2.0), _asset(hours=2000))
    assert prediction.rul_hours < 50
    assert prediction.risk_level == "critical"


def test_rule_based_normal_readings_linear_low_risk():
    estimator = RULEstimator(model_backend="rules")
    asset = _asset(hours=1000)
    prediction = estimator.predict(_history(temp=430.0, vib=2.0), asset)
    assert prediction.rul_hours == 4000.0
    assert prediction.risk_level == "low"


def test_predict_returns_populated_prediction():
    estimator = RULEstimator(model_backend="rules")
    prediction = estimator.predict(_history(temp=460.0, vib=3.0), _asset())
    assert prediction.prediction_id
    assert prediction.asset_id == "ast-1"
    assert 0.0 <= prediction.confidence <= 1.0
    assert prediction.model_used
    assert prediction.recommendation


def test_predict_batch_multiple_assets():
    estimator = RULEstimator(model_backend="rules")
    assets = [(_asset(hours=1000), _history(430.0, 2.0)), (_asset(hours=4800), _history(500.0, 5.5))]
    predictions = estimator.predict_batch(assets)
    assert len(predictions) == 2
    assert predictions[1].risk_level in {"high", "critical"}


def test_get_model_info_contains_backend():
    estimator = RULEstimator(model_backend="rules")
    info = estimator.get_model_info()
    assert info["backend"] == "rules"
    assert "model_loaded" in info
