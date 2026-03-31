"""Geopolitical forecasting module for regional risk outlooks."""

from __future__ import annotations

from typing import Any, Dict, List

from src.apps._shared import clamp, safe_float, utc_now_iso
from src.apps.geopolitical.risk_scorer import RiskScorer
from src.llm_core import Orchestrator, QueryRequest, TaskDomain


class GeopoliticalForecaster:
    """Produces trend + LLM assisted risk forecasts."""

    def __init__(self, risk_scorer: RiskScorer | None = None) -> None:
        self.risk_scorer = risk_scorer or RiskScorer()
        self.orchestrator = Orchestrator()

    def _extract_sections(self, text: str) -> Dict[str, Any]:
        lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        decision_points = [line for line in lines if "decision" in line.lower()]
        preparations = [line for line in lines if "prepare" in line.lower() or "readiness" in line.lower()]
        return {
            "most_likely": lines[0] if lines else "Most likely: continued current posture.",
            "best_case": lines[1] if len(lines) > 1 else "Best case: de-escalation and diplomatic stabilization.",
            "worst_case": lines[2] if len(lines) > 2 else "Worst case: rapid escalation with multi-domain confrontation.",
            "decision_points": decision_points[:5] or ["Force posture review at 72-hour intervals."],
            "preparations": preparations[:5] or ["Increase ISR collection and contingency readiness drills."],
        }

    def _trend_projection(self, score: float, trend: str, horizon_days: int, history: List[dict]) -> str:
        recent = history[-5:]
        avg_delta = sum(safe_float(entry.get("delta")) for entry in recent) / max(1, len(recent))
        projected = clamp(score + (avg_delta * horizon_days), 0.0, 100.0)
        direction = "rising" if avg_delta > 0 else "declining" if avg_delta < 0 else trend
        return f"Score trending {direction} at {avg_delta:.2f}/day — projected {projected:.1f} in {horizon_days} days"

    def forecast(self, region: str, risk_history: List[dict] | None = None, horizon_days: int = 30) -> dict:
        if not isinstance(region, str) or not region.strip():
            raise ValueError("region must be a non-empty string")
        if not isinstance(horizon_days, int) or horizon_days <= 0:
            raise ValueError("horizon_days must be positive integer")
        score_data = self.risk_scorer.get_score(region)
        score = safe_float(score_data["score"])
        trend = str(score_data["trend"])
        history = risk_history if isinstance(risk_history, list) else score_data.get("history", [])
        recent_events = [
            f"{entry.get('reason','event')} ({entry.get('delta', 0):+})"
            for entry in history[-5:]
        ]
        events_summary = ", ".join(recent_events) if recent_events else "No recent events available."
        prompt = (
            f"Based on the current risk score of {score}/100 for {region} with trend {trend}, and recent events: "
            f"{events_summary}, provide a {horizon_days}-day forecast. Include: 1) Most likely scenario "
            "2) Best-case scenario 3) Worst-case scenario 4) Key decision points 5) Recommended preparations. "
            "Classification: UNCLASSIFIED - FOUO."
        )
        try:
            resp = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(resp, "text", "")
            if text and "not yet loaded" not in text.lower() and "pending" not in text.lower():
                sections = self._extract_sections(text)
                confidence = 0.72
            else:
                raise RuntimeError("LLM unavailable")
        except Exception:
            projection = self._trend_projection(score, trend, horizon_days, history)
            sections = {
                "most_likely": projection,
                "best_case": f"If de-escalation succeeds, projected score could drop below {max(0.0, score - 10):.1f}.",
                "worst_case": f"If escalation accelerates, projected score could exceed {min(100.0, score + 20):.1f}.",
                "decision_points": ["Review escalation indicators every 24h.", "Reassess force readiness weekly."],
                "preparations": ["Increase ISR coverage.", "Preposition sustainment assets in low-risk corridors."],
            }
            confidence = 0.55
        return {
            "region": region.strip(),
            "horizon_days": horizon_days,
            "current_risk": score,
            "forecast": sections,
            "confidence": confidence,
            "timestamp": utc_now_iso(),
        }

    def forecast_all(self, horizon_days: int = 30) -> List[dict]:
        if not isinstance(horizon_days, int) or horizon_days <= 0:
            raise ValueError("horizon_days must be positive integer")
        forecasts: List[dict] = []
        for region, payload in self.risk_scorer.get_all_scores().items():
            if safe_float(payload.get("score")) > 30:
                forecasts.append(self.forecast(region=region, risk_history=payload.get("history", []), horizon_days=horizon_days))
        return forecasts
