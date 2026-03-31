"""Explainable AI tooling for tactical autonomy decisions.

Provides operator-facing and analyst-facing explanations for why autonomy
selected a specific action under contested mission conditions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from src.autonomy.models import AutonomyDecision


class DecisionExplainer:
    """Generates structured and plain-language tactical explanations."""

    def __init__(self) -> None:
        try:
            import captum  # noqa: F401  # type: ignore

            self._captum_available = True
        except Exception:
            self._captum_available = False

    def _factorize_context(self, decision: AutonomyDecision) -> List[Dict[str, Any]]:
        factors: List[Dict[str, Any]] = []
        ctx = decision.context or {}
        for key, value in ctx.items():
            influence = "neutral"
            weight = 0.5
            if isinstance(value, (int, float)):
                if key.lower().endswith("risk") or key.lower() in {"risk_score", "threat_level"}:
                    influence = "negative" if float(value) > 0.5 else "neutral"
                    weight = min(1.0, max(0.1, float(value)))
                elif key.lower().endswith("confidence"):
                    influence = "positive" if float(value) > 0.5 else "negative"
                    weight = min(1.0, max(0.1, abs(float(value))))
            factors.append(
                {
                    "factor": key,
                    "value": value,
                    "influence": influence,
                    "weight": round(weight, 3),
                }
            )
        if not factors:
            factors.append(
                {
                    "factor": "context",
                    "value": "limited",
                    "influence": "neutral",
                    "weight": 0.3,
                }
            )
        return factors

    def explain(self, decision: AutonomyDecision) -> Dict[str, Any]:
        """Return structured tactical explanation for an autonomy decision."""
        factors = self._factorize_context(decision)
        used_rl = bool(decision.context.get("rl_policy") or decision.context.get("observation"))
        attribution = "context_based"
        if used_rl and self._captum_available:
            # Captum integration point for observation feature attribution.
            attribution = "captum_feature_attribution_available"

        llm_exchange = None
        if decision.llm_consulted:
            llm_exchange = {
                "prompt": decision.context.get("llm_prompt"),
                "response": decision.context.get("llm_response"),
            }

        return {
            "summary": (
                f"Decision {decision.decision_type.value.upper()} was selected for "
                f"agent {decision.agent_id} with {decision.confidence * 100:.1f}% confidence."
            ),
            "factors": factors,
            "alternatives": decision.alternatives_considered,
            "risk_assessment": {
                "risk_score": decision.risk_score,
                "requires_human_review": decision.requires_human_review,
                "attribution_method": attribution,
            },
            "recommendation": (
                "Proceed with caution and monitor telemetry."
                if decision.risk_score > 0.6
                else "Decision is operationally acceptable under current conditions."
            ),
            "llm_exchange": llm_exchange,
        }

    def explain_for_operator(self, decision: AutonomyDecision) -> str:
        """Generate concise plain-language field explanation."""
        alt_text = "none recorded"
        if decision.alternatives_considered:
            first_alt = decision.alternatives_considered[0]
            alt_text = (
                f"{first_alt.get('option', first_alt.get('action', 'alternative option'))}"
                f" rejected due to {first_alt.get('reason', 'higher tactical risk')}"
            )
        return (
            f"The system chose to {decision.decision_type.value.upper()} because {decision.reasoning}. "
            f"Alternative was {alt_text}. "
            f"Confidence: {decision.confidence * 100:.1f}%. Risk: {decision.risk_score:.2f}."
        )

    def explain_batch(self, decisions: List[AutonomyDecision]) -> Dict[str, Any]:
        """Summarize autonomy behavior over a decision batch."""
        if not decisions:
            return {
                "count": 0,
                "dominant_decision_types": {},
                "confidence_distribution": {"low": 0, "medium": 0, "high": 0},
                "risk_trend": "stable",
            }
        type_counter = Counter(d.decision_type.value for d in decisions)
        low = sum(1 for d in decisions if d.confidence < 0.4)
        high = sum(1 for d in decisions if d.confidence >= 0.7)
        medium = len(decisions) - low - high
        avg_risk_first = sum(d.risk_score for d in decisions[: max(1, len(decisions) // 2)]) / max(
            1, len(decisions[: max(1, len(decisions) // 2)])
        )
        avg_risk_second = sum(d.risk_score for d in decisions[max(1, len(decisions) // 2) :]) / max(
            1, len(decisions[max(1, len(decisions) // 2) :])
        )
        if avg_risk_second > avg_risk_first + 0.05:
            trend = "increasing"
        elif avg_risk_second < avg_risk_first - 0.05:
            trend = "decreasing"
        else:
            trend = "stable"
        return {
            "count": len(decisions),
            "dominant_decision_types": dict(type_counter),
            "confidence_distribution": {"low": low, "medium": medium, "high": high},
            "risk_trend": trend,
        }

