"""
S3M Confidence Framework
Scores orchestration outputs for tactical human-review gating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


@dataclass
class ConfidenceFactors:
    """Factorized confidence components for operator transparency."""

    routing: float
    health: float
    agreement: float
    completeness: float
    failover: float
    verification: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "routing": round(self.routing, 4),
            "health": round(self.health, 4),
            "agreement": round(self.agreement, 4),
            "completeness": round(self.completeness, 4),
            "failover": round(self.failover, 4),
            "verification": round(self.verification, 4),
        }


@dataclass
class ConfidenceScore:
    """Final confidence decision with tactical review guidance."""

    confidence_score: float
    review_status: str
    factors: ConfidenceFactors
    reasoning: List[str]
    penalties_applied: List[str] = field(default_factory=list)
    audit_id: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ConfidenceFramework:
    """
    Deterministic confidence scorer for offline edge deployments.

    Tactical context:
    This class enforces review posture when model health, agreement, or integrity
    signals indicate elevated operational risk.
    """

    def __init__(self) -> None:
        self._history: List[Dict[str, object]] = []

    def score_decision(
        self,
        response_text: str,
        routing_certainty: float,
        engine_health: Dict[str, str],
        engine_responses: Dict[str, str],
        selected_engines: List[str],
        failover_used: bool = False,
        model_drift_detected: bool = False,
        audit_id: Optional[str] = None,
    ) -> ConfidenceScore:
        """Compute confidence and review state from routing/runtime signals."""
        sanitized_text = str(response_text or "").strip()
        routing = _clamp(routing_certainty)
        health = self._health_factor(engine_health)
        agreement = self._agreement_factor(engine_responses, selected_engines)
        completeness = self._completeness_factor(sanitized_text)
        failover = 0.75 if bool(failover_used) else 1.0
        verification = 0.40 if bool(model_drift_detected) else 1.0

        factors = ConfidenceFactors(
            routing=routing,
            health=health,
            agreement=agreement,
            completeness=completeness,
            failover=failover,
            verification=verification,
        )

        score = (
            (factors.routing * 0.30)
            + (factors.health * 0.20)
            + (factors.agreement * 0.15)
            + (factors.completeness * 0.15)
            + (factors.failover * 0.10)
            + (factors.verification * 0.10)
        )

        penalties: List[str] = []
        if failover_used:
            penalties.append("FAILOVER_USED")
            score -= 0.05
        if model_drift_detected:
            penalties.append("MODEL_DRIFT")
            score -= 0.15
        if any(str(state).lower() == "unavailable" for state in engine_health.values()):
            penalties.append("ENGINE_UNAVAILABLE")
            score -= 0.08

        score = _clamp(score)
        if score >= 0.80:
            review_status = "ACCEPT"
        elif score >= 0.60:
            review_status = "REVIEW"
        else:
            review_status = "REJECT"

        reasoning = [
            f"Routing certainty {routing:.0%}.",
            f"Engine health factor {health:.0%}.",
            f"Cross-engine agreement {agreement:.0%}.",
            f"Response completeness {completeness:.0%}.",
            "Failover penalty applied." if failover_used else "No failover penalty.",
            "Model drift penalty applied." if model_drift_detected else "No model drift detected.",
        ]

        result = ConfidenceScore(
            confidence_score=score,
            review_status=review_status,
            factors=factors,
            reasoning=reasoning,
            penalties_applied=penalties,
            audit_id=str(audit_id or "unknown"),
        )
        self._history.append(
            {
                "score": result.confidence_score,
                "status": result.review_status,
                "audit_id": result.audit_id,
                "timestamp": result.timestamp,
                "factors": result.factors.to_dict(),
                "penalties": list(result.penalties_applied),
            }
        )
        if len(self._history) > 500:
            self._history = self._history[-500:]
        return result

    def get_scoring_history(self, limit: int = 50) -> List[Dict[str, object]]:
        bounded = max(1, int(limit))
        return list(self._history[-bounded:])

    @staticmethod
    def _health_factor(engine_health: Dict[str, str]) -> float:
        if not engine_health:
            return 0.5
        score = 0.0
        for state in engine_health.values():
            normalized = str(state or "").lower()
            if normalized == "healthy":
                score += 1.0
            elif normalized == "degraded":
                score += 0.65
            elif normalized == "warming":
                score += 0.50
            else:
                score += 0.20
        return _clamp(score / float(len(engine_health)))

    @staticmethod
    def _agreement_factor(
        engine_responses: Dict[str, str],
        selected_engines: List[str],
    ) -> float:
        if not selected_engines:
            return 0.5
        if len(selected_engines) == 1:
            return 0.9
        texts = [str(engine_responses.get(engine, "")) for engine in selected_engines]
        pairwise: List[float] = []
        for idx in range(len(texts)):
            for jdx in range(idx + 1, len(texts)):
                pairwise.append(SequenceMatcher(None, texts[idx], texts[jdx]).ratio())
        if not pairwise:
            return 0.5
        return _clamp(sum(pairwise) / float(len(pairwise)))

    @staticmethod
    def _completeness_factor(response_text: str) -> float:
        length = len(response_text)
        if length == 0:
            return 0.0
        if length < 40:
            return 0.45
        if length < 120:
            return 0.75
        return 0.95
