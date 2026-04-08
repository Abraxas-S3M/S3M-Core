"""Tests for risk workspace adapter behavior."""

from __future__ import annotations

import services.risk_assessment.bayesian_network as bayesian_module
import src.prediction.risk_forecaster as risk_forecaster_module

from src.api.gui_bridge.adapters.risk_adapter import RiskAdapter


class _FakeThreatProvider:
    def get_threat_stats(self):
        return {
            "total_events": 10,
            "by_level": {"CRITICAL": 2, "HIGH": 3, "MEDIUM": 1},
            "by_category": {"CYBER": 5, "AIR": 5},
            "active_sensors": 4,
        }


class _BrokenThreatProvider:
    def get_threat_stats(self):
        raise RuntimeError("provider unavailable")


def test_get_metrics_builds_domains_composite_and_forecast(monkeypatch) -> None:
    adapter = RiskAdapter()
    adapter._threat = _FakeThreatProvider()

    metrics = adapter.get_metrics()
    assert 0 <= metrics.composite <= 100
    assert len(metrics.domains) == 4
    assert [d.domain for d in metrics.domains] == ["air", "cyber", "intel", "logistics"]
    assert len(metrics.forecast) == 4
    assert all(0 <= point.score <= 100 for point in metrics.forecast)
    assert any(driver.name == "ISR coverage active" for driver in metrics.drivers)


def test_get_threat_stats_falls_back_on_provider_error(monkeypatch) -> None:
    adapter = RiskAdapter()
    adapter._threat = _BrokenThreatProvider()
    fallback = adapter._get_threat_stats()
    assert fallback == {"total_events": 0, "by_level": {}, "by_category": {}, "active_sensors": 0}


def test_compute_composite_defaults_when_no_domains() -> None:
    assert RiskAdapter._compute_composite([]) == 50


def test_build_forecast_uses_risk_forecaster_when_available(monkeypatch) -> None:
    captured = {}

    class _FakeForecaster:
        def forecast(self, historical_scores, horizon_hours: int = 24):
            captured["history"] = historical_scores
            captured["horizon"] = horizon_hours
            return [41.9, -4.0, 130.4, 55.2]

    monkeypatch.setattr(risk_forecaster_module, "RiskForecaster", _FakeForecaster)
    adapter = RiskAdapter()

    forecast = adapter._build_forecast(40)
    assert captured["horizon"] == 4
    assert captured["history"][-1][1] == 40.0
    assert [point.score for point in forecast] == [42, 0, 100, 55]
    assert len(forecast) == 4


def test_build_forecast_falls_back_when_forecaster_fails(monkeypatch) -> None:
    class _BrokenForecaster:
        def forecast(self, historical_scores, horizon_hours: int = 24):
            raise RuntimeError("forecaster unavailable")

    monkeypatch.setattr(risk_forecaster_module, "RiskForecaster", _BrokenForecaster)
    adapter = RiskAdapter()

    forecast = adapter._build_forecast(50)
    assert [point.score for point in forecast] == [50, 50, 50, 50]
    assert len(forecast) == 4


def test_get_what_if_returns_bayesian_evaluation(monkeypatch) -> None:
    class _FakeBayesianNetwork:
        def evaluate(self, scenario: dict):
            return {"overallScore": 61, "scenarioEcho": scenario}

    monkeypatch.setattr(bayesian_module, "BayesianNetwork", _FakeBayesianNetwork, raising=False)
    adapter = RiskAdapter()
    scenario = {"threat": "high", "readiness": "low"}

    result = adapter.get_what_if(scenario)
    assert result["scenario"] == scenario
    assert result["result"]["overallScore"] == 61
    assert result["result"]["scenarioEcho"] == scenario
    assert "updatedAt" in result


def test_get_what_if_falls_back_on_errors(monkeypatch) -> None:
    class _BrokenBayesianNetwork:
        def __init__(self):
            raise RuntimeError("init failure")

    monkeypatch.setattr(bayesian_module, "BayesianNetwork", _BrokenBayesianNetwork, raising=False)
    adapter = RiskAdapter()
    scenario = {"threat": "low"}

    result = adapter.get_what_if(scenario)
    assert result["scenario"] == scenario
    assert result["result"] == {}
    assert "updatedAt" in result
