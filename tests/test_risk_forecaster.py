"""Unit tests for tactical risk forecasting and operational persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import src.prediction.risk_forecaster as risk_forecaster_module
from src.prediction.risk_forecaster import OperationalStore, RiskForecaster


def test_forecast_uses_linear_fallback_and_persists_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(risk_forecaster_module, "_Prophet", None)
    store = OperationalStore(db_path=str(tmp_path / "operational.sqlite3"))
    forecaster = RiskForecaster(store=store, max_history=64)

    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [
        (anchor, 10.0),
        (anchor + timedelta(hours=1), 20.0),
        (anchor + timedelta(hours=2), 30.0),
    ]

    forecast = forecaster.forecast(history, horizon_hours=3)
    assert forecast == pytest.approx([40.0, 50.0, 60.0], abs=1e-6)

    persisted = store.get_recent_risk_scores(limit=10)
    assert len(persisted) == 3
    assert [score for _, score in persisted] == [10.0, 20.0, 30.0]


def test_forecast_validates_inputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(risk_forecaster_module, "_Prophet", None)
    forecaster = RiskForecaster(store=OperationalStore(db_path=str(tmp_path / "risk.sqlite3")))

    with pytest.raises(ValueError):
        forecaster.forecast([("not-a-datetime", 50.0)], horizon_hours=2)  # type: ignore[list-item]

    with pytest.raises(ValueError):
        forecaster.forecast([], horizon_hours=0)


def test_forecast_clamps_scores_to_tactical_bounds(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(risk_forecaster_module, "_Prophet", None)
    store = OperationalStore(db_path=str(tmp_path / "risk_bounds.sqlite3"))
    forecaster = RiskForecaster(store=store)

    anchor = datetime(2026, 2, 1, tzinfo=timezone.utc)
    forecast = forecaster.forecast(
        [
            (anchor, 95.0),
            (anchor + timedelta(hours=1), 120.0),
        ],
        horizon_hours=2,
    )

    assert forecast == [100.0, 100.0]
