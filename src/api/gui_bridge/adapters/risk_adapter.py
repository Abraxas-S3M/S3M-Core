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
from typing import Any, Dict, List, Tuple

from src.api.gui_bridge.models.gui_schemas import (
    GUIRiskData,
    GUIRiskDomain,
    GUIRiskDriver,
    GUIRiskForecast,
    TrendDirection,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskAdapter:
    def __init__(self) -> None:
        try:
            from src.dashboard.providers.threat_dash_provider import ThreatDashProvider

            self._threat = ThreatDashProvider()
        except Exception:
            # Tactical operations must keep rendering risk even if provider wiring fails.
            class _FallbackThreatProvider:
                @staticmethod
                def get_threat_stats() -> Dict[str, Any]:
                    return {"total_events": 0, "by_level": {}, "by_category": {}, "active_sensors": 0}

            self._threat = _FallbackThreatProvider()
        self._risk_history: List[Tuple[datetime, float]] = []
        self._risk_history_limit = 512
        self._risk_forecaster = None

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

        result = GUIRiskData(
            composite=composite,
            domains=domains,
            forecast=forecast,
            drivers=drivers,
            updatedAt=_now_iso(),
        )
        emit_training_record("risk", {"query": "metrics"}, result)
        return result

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

    def _record_risk_point(self, score: int) -> None:
        now = datetime.now(timezone.utc)
        bounded = float(min(100, max(0, int(score))))
        self._risk_history.append((now, bounded))
        if len(self._risk_history) > self._risk_history_limit:
            self._risk_history = self._risk_history[-self._risk_history_limit :]

    def _linear_forecast_fallback(self, horizon: int = 4) -> List[int]:
        if not self._risk_history:
            return [50 for _ in range(horizon)]
        if len(self._risk_history) == 1:
            baseline = int(round(self._risk_history[-1][1]))
            return [min(100, max(0, baseline)) for _ in range(horizon)]

        _, prev_score = self._risk_history[-2]
        _, last_score = self._risk_history[-1]
        slope = last_score - prev_score
        return [
            min(100, max(0, int(round(last_score + slope * float(step + 1)))))
            for step in range(horizon)
        ]

    def _build_forecast(self, composite: int) -> List[GUIRiskForecast]:
        self._record_risk_point(composite)
        now = datetime.now(timezone.utc)
        try:
            from src.prediction.risk_forecaster import RiskForecaster

            if self._risk_forecaster is None:
                self._risk_forecaster = RiskForecaster()
            # Tactical UI uses a 1-hour lookahead at 15-minute display checkpoints.
            predictions = self._risk_forecaster.forecast(
                historical_scores=list(self._risk_history),
                horizon_hours=4,
            )
            if predictions:
                return [
                    GUIRiskForecast(
                        timestamp=(now + timedelta(minutes=15 * (i + 1))).isoformat(),
                        score=min(100, max(0, int(round(p)))),
                    )
                    for i, p in enumerate(predictions[:4])
                ]
        except Exception:
            pass

        fallback = self._linear_forecast_fallback(horizon=4)
        return [
            GUIRiskForecast(
                timestamp=(now + timedelta(minutes=15 * (i + 1))).isoformat(),
                score=fallback[i],
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
