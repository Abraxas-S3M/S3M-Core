from __future__ import annotations

from src.apps.geopolitical.event_analyzer import EventAnalyzer
from src.apps.geopolitical.geopolitical_forecaster import GeopoliticalForecaster
from src.apps.geopolitical.geopolitical_module import GeopoliticalModule
from src.apps.geopolitical.risk_scorer import RiskScorer


def test_risk_scorer_update_and_clamp() -> None:
    scorer = RiskScorer()
    scorer.update_score("Red Sea", 150.0, "severe incident")
    assert scorer.get_score("Red Sea")["score"] == 100.0
    scorer.update_score("Red Sea", -300.0, "reset")
    assert scorer.get_score("Red Sea")["score"] == 0.0


def test_risk_decay_reduces_scores() -> None:
    scorer = RiskScorer()
    scorer.update_score("Levant", 20.0, "baseline")
    before = scorer.get_score("Levant")["score"]
    scorer.apply_decay(hours_elapsed=2.0)
    after = scorer.get_score("Levant")["score"]
    assert after < before


def test_get_high_risk_regions_filters() -> None:
    scorer = RiskScorer()
    scorer.update_score("Region A", 80.0, "critical")
    scorer.update_score("Region B", 20.0, "minor")
    highs = scorer.get_high_risk_regions(70)
    assert len(highs) == 1
    assert highs[0]["region"] == "Region A"


def test_event_analyzer_returns_impact_field() -> None:
    analyzer = EventAnalyzer()
    result = analyzer.analyze("Hostile naval posturing detected", region="Red Sea")
    assert isinstance(result, dict)
    assert "impact" in result


def test_event_analyzer_llm_fallback() -> None:
    analyzer = EventAnalyzer()
    result = analyzer.analyze("Routine diplomatic meeting", region="Arabian Peninsula")
    assert "raw_analysis" in result
    assert isinstance(result["raw_analysis"], str)


def test_forecaster_structured_forecast() -> None:
    scorer = RiskScorer()
    scorer.update_score("Horn of Africa", 40.0, "elevated activity")
    forecaster = GeopoliticalForecaster(risk_scorer=scorer)
    result = forecaster.forecast("Horn of Africa", horizon_days=15)
    assert result["region"] == "Horn of Africa"
    assert "forecast" in result
    assert "most_likely" in result["forecast"]


def test_geopolitical_module_health() -> None:
    module = GeopoliticalModule()
    status = module.health_check()
    assert status["status"] in {"ready", "operational"}
