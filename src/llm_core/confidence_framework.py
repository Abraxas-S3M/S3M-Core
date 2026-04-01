"""
S3M Confidence Framework v1.0
Transparent uncertainty quantification with explainable scoring.

This module assigns a confidence score to every orchestrated decision and
produces a review posture suitable for mission-time human oversight.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger("s3m.confidence")


# ===== CONFIGURATION CONSTANTS =====

# Confidence decision thresholds
ACCEPT_THRESHOLD = 0.80  # >= 80%: ACCEPT (auto-approve)
REVIEW_THRESHOLD = 0.60  # >= 60%: REVIEW (human check required)
# < 60%: REJECT (escalate immediately)

# Factor weights (must sum to exactly 1.0)
WEIGHT_ROUTING = 0.25
WEIGHT_HEALTH = 0.20
WEIGHT_AGREEMENT = 0.20
WEIGHT_COMPLETENESS = 0.15
WEIGHT_FAILOVER = 0.10
WEIGHT_VERIFICATION = 0.10

# Verify weights sum to 1.0
_WEIGHT_SUM = (
    WEIGHT_ROUTING
    + WEIGHT_HEALTH
    + WEIGHT_AGREEMENT
    + WEIGHT_COMPLETENESS
    + WEIGHT_FAILOVER
    + WEIGHT_VERIFICATION
)
if abs(_WEIGHT_SUM - 1.0) >= 0.001:
    raise RuntimeError(f"Weights must sum to 1.0, got {_WEIGHT_SUM}")

# Penalty multipliers (applied post-aggregation)
FAILOVER_PENALTY_FACTOR = 0.85  # 15% penalty
DRIFT_PENALTY_FACTOR = 0.80  # 20% penalty
LOW_HEALTH_PENALTY_FACTOR = 0.90  # 10% penalty
DISAGREEMENT_PENALTY_FACTOR = 0.85  # 15% penalty

# Health state scoring map
HEALTH_STATE_SCORES = {
    "HEALTHY": 1.0,
    "DEGRADED": 0.7,
    "UNAVAILABLE": 0.0,
    "WARMING": 0.5,
    "UNKNOWN": 0.6,
}

# Response quality thresholds
MIN_RESPONSE_LENGTH = 50
GOOD_RESPONSE_LENGTH = 100
MIN_SENTENCE_COUNT = 1
GOOD_SENTENCE_COUNT = 3


class ReviewStatus(Enum):
    """Decision status for confidence-based gating."""

    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass
class ConfidenceFactors:
    """Individual confidence scoring factors (0.0-1.0 each)."""

    routing_certainty: float
    engine_health: float
    agreement_strength: float
    response_completeness: float
    failover_penalty: float
    model_verification: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class ConfidenceScore:
    """Complete confidence assessment result."""

    confidence_score: float
    review_status: str
    factors: ConfidenceFactors
    base_score_before_penalties: float
    reasoning: List[str]
    penalties_applied: List[str]
    audit_id: str

    def is_acceptable(self) -> bool:
        return self.review_status == ReviewStatus.ACCEPT.value

    def needs_review(self) -> bool:
        return self.review_status in (ReviewStatus.REVIEW.value, ReviewStatus.REJECT.value)

    def to_dict(self) -> Dict[str, object]:
        return {
            "confidence_score": round(self.confidence_score, 4),
            "review_status": self.review_status,
            "base_score_before_penalties": round(self.base_score_before_penalties, 4),
            "factors": self.factors.to_dict(),
            "reasoning": list(self.reasoning),
            "penalties_applied": list(self.penalties_applied),
            "audit_id": self.audit_id,
        }

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CONFIDENCE ASSESSMENT SUMMARY",
            "=" * 60,
            f"Final Confidence Score: {self.confidence_score:.1%}",
            f"Review Status: {self.review_status}",
            f"Audit ID: {self.audit_id}",
            "",
            f"BASE SCORE (before penalties): {self.base_score_before_penalties:.1%}",
            "",
            "INDIVIDUAL FACTORS:",
            f"  Routing Certainty:      {self.factors.routing_certainty:.1%} (weight: 25%)",
            f"  Engine Health:          {self.factors.engine_health:.1%} (weight: 20%)",
            f"  Agreement Strength:     {self.factors.agreement_strength:.1%} (weight: 20%)",
            f"  Response Completeness:  {self.factors.response_completeness:.1%} (weight: 15%)",
            f"  Failover Penalty:       {self.factors.failover_penalty:.1%} (weight: 10%)",
            f"  Model Verification:     {self.factors.model_verification:.1%} (weight: 10%)",
        ]

        if self.penalties_applied:
            lines.append("")
            lines.append("PENALTIES APPLIED:")
            for penalty in self.penalties_applied:
                lines.append(f"  - {penalty}")
            if self.base_score_before_penalties > 0:
                penalty_impact = (
                    (self.base_score_before_penalties - self.confidence_score)
                    / self.base_score_before_penalties
                    * 100
                )
                lines.append(f"  Total penalty impact: {penalty_impact:.0f}%")

        lines.append("")
        lines.append("REASONING:")
        for index, reason in enumerate(self.reasoning, start=1):
            lines.append(f"  {index}. {reason}")

        lines.extend(
            [
                "",
                "DECISION THRESHOLD:",
                f"  ACCEPT threshold:  >= {ACCEPT_THRESHOLD:.0%}",
                f"  REVIEW threshold:  >= {REVIEW_THRESHOLD:.0%}",
                f"  REJECT threshold:  <  {REVIEW_THRESHOLD:.0%}",
                "=" * 60,
            ]
        )
        return "\n".join(lines)


@dataclass
class ConfidenceInput:
    """Input payload for confidence scoring."""

    response_text: str
    routing_certainty: float
    engine_health: Dict[str, str]
    engine_responses: Dict[str, str]
    selected_engines: List[str]
    failover_used: bool
    model_drift_detected: bool

    def validate(self) -> Tuple[bool, Optional[str]]:
        if not 0.0 <= self.routing_certainty <= 1.0:
            return False, f"routing_certainty must be in [0, 1], got {self.routing_certainty}"

        if self.response_text is None:
            return False, "response_text cannot be None"

        if not self.selected_engines:
            return False, "selected_engines cannot be empty"

        for engine_id, health in self.engine_health.items():
            if health not in HEALTH_STATE_SCORES:
                return False, f"Unknown health state '{health}' for {engine_id}"

        return True, None


class ConfidenceFramework:
    """
    Compute transparent confidence scores for LLM decisions.

    Tactical context:
    - The score is designed for mission-time trust gating where low certainty
      must force review or rejection before autonomous action.
    """

    def __init__(self) -> None:
        logger.info("ConfidenceFramework initialized")
        self._scoring_history: List[Dict[str, object]] = []

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
        """Score one routed decision using six weighted factors."""
        audit_id = audit_id or str(uuid.uuid4())[:8]

        input_obj = ConfidenceInput(
            response_text=response_text,
            routing_certainty=routing_certainty,
            engine_health=engine_health,
            engine_responses=engine_responses,
            selected_engines=selected_engines,
            failover_used=failover_used,
            model_drift_detected=model_drift_detected,
        )
        is_valid, error = input_obj.validate()
        if not is_valid:
            logger.error("Invalid confidence input: %s", error)
            raise ValueError(error)

        factor_routing = routing_certainty
        factor_health = self._calculate_health_score(engine_health, selected_engines)
        factor_agreement = self._calculate_agreement_score(engine_responses, selected_engines)
        factor_completeness = self._calculate_completeness_score(response_text)
        factor_failover = 1.0 if not failover_used else FAILOVER_PENALTY_FACTOR
        factor_verification = 1.0 if not model_drift_detected else DRIFT_PENALTY_FACTOR

        factors = ConfidenceFactors(
            routing_certainty=factor_routing,
            engine_health=factor_health,
            agreement_strength=factor_agreement,
            response_completeness=factor_completeness,
            failover_penalty=factor_failover,
            model_verification=factor_verification,
        )

        base_score = (
            (WEIGHT_ROUTING * factor_routing)
            + (WEIGHT_HEALTH * factor_health)
            + (WEIGHT_AGREEMENT * factor_agreement)
            + (WEIGHT_COMPLETENESS * factor_completeness)
            + (WEIGHT_FAILOVER * factor_failover)
            + (WEIGHT_VERIFICATION * factor_verification)
        )

        final_score = base_score
        penalties_applied: List[str] = []

        if failover_used:
            final_score *= FAILOVER_PENALTY_FACTOR
            penalties_applied.append(
                f"Failover used ({(1.0 - FAILOVER_PENALTY_FACTOR) * 100:.0f}% penalty)"
            )

        if model_drift_detected:
            final_score *= DRIFT_PENALTY_FACTOR
            penalties_applied.append(
                f"Model drift detected ({(1.0 - DRIFT_PENALTY_FACTOR) * 100:.0f}% penalty)"
            )

        if factor_health < 0.7:
            final_score *= LOW_HEALTH_PENALTY_FACTOR
            penalties_applied.append(
                f"Low engine health ({(1.0 - LOW_HEALTH_PENALTY_FACTOR) * 100:.0f}% penalty)"
            )

        if factor_agreement < 0.6:
            final_score *= DISAGREEMENT_PENALTY_FACTOR
            penalties_applied.append(
                f"Low engine agreement ({(1.0 - DISAGREEMENT_PENALTY_FACTOR) * 100:.0f}% penalty)"
            )

        final_score = min(max(final_score, 0.0), 1.0)

        if factor_completeness == 0.0:
            review_status = ReviewStatus.REJECT.value
        elif final_score >= ACCEPT_THRESHOLD:
            review_status = ReviewStatus.ACCEPT.value
        elif final_score >= REVIEW_THRESHOLD:
            review_status = ReviewStatus.REVIEW.value
        else:
            review_status = ReviewStatus.REJECT.value

        reasoning = self._build_reasoning(factors=factors, response_text=response_text)
        score = ConfidenceScore(
            confidence_score=final_score,
            review_status=review_status,
            factors=factors,
            base_score_before_penalties=base_score,
            reasoning=reasoning,
            penalties_applied=penalties_applied,
            audit_id=audit_id,
        )

        logger.info(
            "[%s] Confidence %.1f%% -> %s (routing=%.1f%% health=%.1f%% agreement=%.1f%%)",
            audit_id,
            final_score * 100.0,
            review_status,
            factor_routing * 100.0,
            factor_health * 100.0,
            factor_agreement * 100.0,
        )
        self._scoring_history.append(
            {
                "audit_id": audit_id,
                "timestamp": datetime.utcnow().isoformat(),
                "score": final_score,
                "status": review_status,
            }
        )
        return score

    def _calculate_health_score(
        self,
        engine_health: Dict[str, str],
        selected_engines: List[str],
    ) -> float:
        """Calculate health factor from selected engine states."""
        if not selected_engines:
            logger.warning("No selected engines, defaulting health score to UNKNOWN baseline")
            return 0.6

        scores: List[float] = []
        for engine_id in selected_engines:
            status = engine_health.get(engine_id, "UNKNOWN")
            score = HEALTH_STATE_SCORES.get(status, 0.6)
            scores.append(score)
            logger.debug("Engine %s health=%s score=%.2f", engine_id, status, score)

        avg_health = sum(scores) / len(scores) if scores else 0.6
        return min(max(avg_health, 0.0), 1.0)

    def _calculate_agreement_score(
        self,
        engine_responses: Dict[str, str],
        selected_engines: List[str],
    ) -> float:
        """Calculate agreement factor from pairwise response similarity."""
        selected_responses = [engine_responses.get(engine_id, "") for engine_id in selected_engines]

        if len(selected_responses) <= 1:
            return 1.0

        non_empty = [response for response in selected_responses if response.strip()]
        if len(non_empty) <= 1:
            logger.debug("Insufficient non-empty responses, agreement defaults to 0.5")
            return 0.5

        similarities: List[float] = []
        for index, text_1 in enumerate(non_empty):
            for text_2 in non_empty[index + 1 :]:
                similarities.append(self._calculate_text_similarity(text_1, text_2))

        if not similarities:
            return 0.5

        avg_similarity = sum(similarities) / len(similarities)
        return min(max(avg_similarity, 0.0), 1.0)

    def _calculate_completeness_score(self, response_text: str) -> float:
        """Estimate structural completeness of the response text."""
        if not response_text or not response_text.strip():
            return 0.0

        text = response_text.strip()
        score = 0.5

        if len(text) > GOOD_RESPONSE_LENGTH:
            score += 0.25
        elif len(text) > MIN_RESPONSE_LENGTH:
            score += 0.15

        sentences = [sentence for sentence in text.split(".") if sentence.strip()]
        sentence_count = len(sentences)
        if sentence_count >= GOOD_SENTENCE_COUNT:
            score += 0.20
        elif sentence_count >= MIN_SENTENCE_COUNT:
            score += 0.10

        if text[0].isupper():
            score += 0.05

        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _calculate_text_similarity(text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two responses."""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        similarity = intersection / union if union else 0.0
        return min(max(similarity, 0.0), 1.0)

    def _build_reasoning(
        self,
        factors: ConfidenceFactors,
        response_text: str,
    ) -> List[str]:
        """Build transparent human-readable reasoning for all factors."""
        reasons: List[str] = []

        if factors.routing_certainty >= 0.9:
            reasons.append(
                f"Routing Certainty {factors.routing_certainty:.0%}: very confident engine selection."
            )
        elif factors.routing_certainty >= 0.75:
            reasons.append(
                f"Routing Certainty {factors.routing_certainty:.0%}: confident engine selection."
            )
        elif factors.routing_certainty >= 0.6:
            reasons.append(
                f"Routing Certainty {factors.routing_certainty:.0%}: moderate confidence in selection."
            )
        else:
            reasons.append(
                f"Routing Certainty {factors.routing_certainty:.0%}: low confidence due to ambiguity."
            )

        if factors.engine_health >= 0.95:
            reasons.append(
                f"Engine Health {factors.engine_health:.0%}: all selected engines healthy."
            )
        elif factors.engine_health >= 0.85:
            reasons.append(
                f"Engine Health {factors.engine_health:.0%}: mostly healthy with minor degradation."
            )
        elif factors.engine_health >= 0.7:
            reasons.append(
                f"Engine Health {factors.engine_health:.0%}: mixed health, some degradation."
            )
        else:
            reasons.append(
                f"Engine Health {factors.engine_health:.0%}: significant health issues detected."
            )

        if factors.agreement_strength >= 0.9:
            reasons.append(
                f"Agreement Strength {factors.agreement_strength:.0%}: strong multi-engine agreement."
            )
        elif factors.agreement_strength >= 0.75:
            reasons.append(
                f"Agreement Strength {factors.agreement_strength:.0%}: good agreement."
            )
        elif factors.agreement_strength >= 0.6:
            reasons.append(
                f"Agreement Strength {factors.agreement_strength:.0%}: moderate agreement."
            )
        else:
            reasons.append(
                f"Agreement Strength {factors.agreement_strength:.0%}: substantial disagreement."
            )

        if factors.response_completeness >= 0.9:
            reasons.append(
                f"Response Completeness {factors.response_completeness:.0%}: well-formed and detailed."
            )
        elif factors.response_completeness >= 0.75:
            reasons.append(
                f"Response Completeness {factors.response_completeness:.0%}: acceptable quality."
            )
        elif factors.response_completeness >= 0.6:
            reasons.append(
                f"Response Completeness {factors.response_completeness:.0%}: somewhat incomplete."
            )
        elif factors.response_completeness > 0.0:
            reasons.append(
                f"Response Completeness {factors.response_completeness:.0%}: very brief or poorly formed."
            )
        else:
            reasons.append(
                "Response Completeness 0%: EMPTY RESPONSE (automatic REJECT posture)."
            )

        if factors.failover_penalty == 1.0:
            reasons.append("Failover Status: not used; primary routing remained stable.")
        else:
            penalty_pct = (1.0 - factors.failover_penalty) * 100
            reasons.append(
                f"Failover Status: used ({penalty_pct:.0f}% penalty due to degraded primary path)."
            )

        if factors.model_verification == 1.0:
            reasons.append("Model Verification: model integrity checks passed.")
        else:
            penalty_pct = (1.0 - factors.model_verification) * 100
            reasons.append(
                f"Model Verification: drift detected ({penalty_pct:.0f}% verification penalty)."
            )

        if not response_text.strip():
            # Tactical context: empty guidance is operationally unsafe and must be explicit.
            reasons.append("Operational Safeguard: empty output is non-actionable and requires escalation.")

        return reasons

    def get_scoring_history(self, limit: int = 20) -> List[Dict[str, object]]:
        """Return recent confidence events for audit review."""
        if limit <= 0:
            return []
        return self._scoring_history[-limit:]

    def clear_history(self) -> None:
        """Clear local history (primarily for test isolation)."""
        self._scoring_history.clear()
