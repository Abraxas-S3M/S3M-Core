"""Geopolitical risk module orchestrator."""

from __future__ import annotations

from typing import Any

from src.apps._shared import safe_float, utc_now_iso
from src.apps.geopolitical.event_analyzer import EventAnalyzer
from src.apps.geopolitical.geopolitical_forecaster import GeopoliticalForecaster
from src.apps.geopolitical.risk_scorer import RiskScorer


class GeopoliticalModule:
    """Coordinate geopolitical analysis, scoring, and forecasts."""

    def __init__(self) -> None:
        self.risk_scorer = RiskScorer()
        self.event_analyzer = EventAnalyzer()
        self.forecaster = GeopoliticalForecaster(self.risk_scorer)
        self._analyses: list[dict[str, Any]] = []
        self.risk_decay_per_hour = 1.0

    def analyze_event(self, description: str, region: str | None = None) -> dict[str, Any]:
        """Run event analysis then update regional risk score."""
        result = self.event_analyzer.analyze(description, region=region)
        impact = str(result.get("impact", "UNKNOWN")).upper()
        delta_map = {"CRITICAL": 15.0, "HIGH": 8.0, "MEDIUM": 3.0, "LOW": 1.0}
        delta = delta_map.get(impact, 0.0)
        if region:
            self.risk_scorer.update_score(region, delta, reason=f"Event impact={impact}: {description[:120]}")
        self._analyses.append(result)
        return result

    def get_risks(self) -> dict[str, dict[str, Any]]:
        """Return all current risk scores."""
        return self.risk_scorer.get_all_scores()

    def get_forecast(self, region: str, days: int = 30) -> dict[str, Any]:
        """Forecast risk outlook for a region."""
        return self.forecaster.forecast(region, horizon_days=days)

    def get_landscape(self) -> dict[str, Any]:
        """Return consolidated geopolitical landscape."""
        risks = self.get_risks()
        forecasts = self.forecaster.forecast_all(horizon_days=30)
        high = self.risk_scorer.get_high_risk_regions(70)
        return {
            "risks": risks,
            "recent_analyses": self._analyses[-25:],
            "forecasts": forecasts,
            "high_risk_regions": high,
            "summary": f"Tracked regions={len(risks)}, high-risk={len(high)}",
            "timestamp": utc_now_iso(),
        }

    def health_check(self) -> dict[str, Any]:
        """Report module health."""
        return {
            "status": "ready",
            "regions_tracked": len(self.risk_scorer.get_all_scores()),
            "analyses_cached": len(self._analyses),
            "risk_decay_per_hour": safe_float(self.risk_decay_per_hour, 1.0),
            "timestamp": utc_now_iso(),
        }

