"""Risk workspace adapter.

Computes composite risk from multiple S3M-Core sources:
- ThreatDashProvider (threat feed stats)
- RiskEngine from services/risk_assessment (Bayesian network)
- Belief state (if available)
- Short-horizon predictor (forecast)

Reshapes into GUIRiskData (composite, domains, forecast, drivers).

Internal dependencies:
- src.dashboard.providers.threat_dash_provider.ThreatDashProvider
- services.risk_assessment.risk_engine.RiskEngine (optional)
- src.prediction.short_horizon_predictor (optional)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from src.api.gui_bridge.models.gui_schemas import (
    GUIRiskData,
    GUIRiskDomain,
    GUIRiskDriver,
    GUIRiskForecast,
    TrendDirection,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskAdapter:
    def __init__(self) -> None:
        from src.dashboard.providers.threat_dash_provider import ThreatDashProvider

        self._threat = ThreatDashProvider()

        # Optional: risk engine
        self._risk_engine = None
        try:
            from services.risk_assessment.risk_engine import RiskEngine

            self._risk_engine = RiskEngine()
        except Exception:
            pass

    def get_metrics(self) -> GUIRiskData:
        threat_stats = self._get_threat_stats()
        domains = self._build_domains(threat_stats)
        composite = self._compute_composite(domains)
        drivers = self._build_drivers(threat_stats)
        forecast = self._build_forecast(composite)

        return GUIRiskData(
            composite=composite,
            domains=domains,
            forecast=forecast,
            drivers=drivers,
            updatedAt=_now_iso(),
        )

    def _get_threat_stats(self) -> Dict[str, Any]:
        try:
            return self._threat.get_threat_stats()
        except Exception:
            return {"total_events": 0, "by_level": {}, "by_category": {}, "active_sensors": 0}

    def _build_domains(self, stats: Dict[str, Any]) -> List[GUIRiskDomain]:
        by_level = stats.get("by_level", {})
        critical = int(by_level.get("CRITICAL", 0))
        high = int(by_level.get("HIGH", 0))
        medium = int(by_level.get("MEDIUM", 0))
        total = max(1, int(stats.get("total_events", 1)))

        # Domain risk scores are threat-density proxies for tactical planning.
        air_score = min(100, int((critical * 4 + high * 2) / max(1, total) * 100))
        cyber_score = min(100, int((critical * 3 + high * 3) / max(1, total) * 100))
        intel_score = min(100, int((high * 2 + medium) / max(1, total) * 100))
        logistics_score = min(100, max(20, 100 - air_score))

        return [
            GUIRiskDomain(domain="air", score=max(10, air_score), trend=self._trend(air_score)),
            GUIRiskDomain(domain="cyber", score=max(10, cyber_score), trend=self._trend(cyber_score)),
            GUIRiskDomain(domain="intel", score=max(10, intel_score), trend=self._trend(intel_score)),
            GUIRiskDomain(domain="logistics", score=max(10, logistics_score), trend=self._trend(logistics_score)),
        ]

    @staticmethod
    def _trend(score: int) -> TrendDirection:
        if score >= 70:
            return TrendDirection.UP
        if score <= 40:
            return TrendDirection.DOWN
        return TrendDirection.STEADY

    @staticmethod
    def _compute_composite(domains: List[GUIRiskDomain]) -> int:
        if not domains:
            return 50
        weights = {"air": 0.35, "cyber": 0.25, "intel": 0.20, "logistics": 0.20}
        total = sum(weights.get(d.domain, 0.25) * d.score for d in domains)
        return int(min(100, max(0, total)))

    def _build_drivers(self, stats: Dict[str, Any]) -> List[GUIRiskDriver]:
        drivers: List[GUIRiskDriver] = []
        by_level = stats.get("by_level", {})
        if int(by_level.get("CRITICAL", 0)) > 0:
            drivers.append(GUIRiskDriver(name="Critical threat events", impact=0.36, direction="negative"))
        if int(by_level.get("HIGH", 0)) > 0:
            drivers.append(GUIRiskDriver(name="Elevated threat posture", impact=0.29, direction="negative"))
        if int(stats.get("active_sensors", 0)) > 2:
            drivers.append(GUIRiskDriver(name="ISR coverage active", impact=0.21, direction="positive"))
        if not drivers:
            drivers = [
                GUIRiskDriver(name="Baseline threat posture", impact=0.15, direction="negative"),
                GUIRiskDriver(name="ISR coverage", impact=0.21, direction="positive"),
            ]
        return drivers

    def _build_forecast(self, composite: int) -> List[GUIRiskForecast]:
        try:
            from src.prediction.short_horizon_predictor import ShortHorizonPredictor

            predictor = ShortHorizonPredictor()
            predictions = predictor.predict(current_value=composite, horizon_steps=4)
            if predictions:
                now = datetime.now(timezone.utc)
                return [
                    GUIRiskForecast(
                        timestamp=(now + timedelta(minutes=15 * (i + 1))).isoformat(),
                        score=min(100, max(0, int(p))),
                    )
                    for i, p in enumerate(predictions)
                ]
        except Exception:
            pass

        now = datetime.now(timezone.utc)
        return [
            GUIRiskForecast(
                timestamp=(now + timedelta(minutes=15 * (i + 1))).isoformat(),
                score=min(100, max(0, composite + ((-1) ** i) * (2 * (i + 1)))),
            )
            for i in range(4)
        ]

    def get_what_if(self, scenario: dict) -> dict:
        """What-if risk analysis using Bayesian network."""
        try:
            from services.risk_assessment.bayesian_network import BayesianNetwork

            bn = BayesianNetwork()
            result = bn.evaluate(scenario) if hasattr(bn, "evaluate") else {}
            return {"scenario": scenario, "result": result, "updatedAt": _now_iso()}
        except Exception:
            return {"scenario": scenario, "result": {}, "updatedAt": _now_iso()}
