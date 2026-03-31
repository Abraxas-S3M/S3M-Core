"""Assurance checks for tactical autonomy decisions.

Applies safety and command-authority policy checks before autonomous actions are
considered approved, routing risky decisions to human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.autonomy.models import AutonomyDecision, DecisionType


@dataclass
class _ReviewRecord:
    decision_id: str
    reviewer: str
    approved: bool
    reason: str


class AssuranceChecker:
    """Evaluates autonomy decisions against tactical assurance rules."""

    def __init__(self, risk_threshold: float = 0.7, confidence_threshold: float = 0.3) -> None:
        self.risk_threshold = float(risk_threshold)
        self.confidence_threshold = float(confidence_threshold)
        self._review_queue: Dict[str, AutonomyDecision] = {}
        self._history: Dict[str, _ReviewRecord] = {}

    def check(self, decision: AutonomyDecision) -> Dict[str, object]:
        """Return assurance verdict and set review flag where required."""
        flags: List[str] = []
        approved = True
        reason = "Decision approved under current assurance policy."

        if decision.risk_score > self.risk_threshold:
            flags.append("high_risk_score")
        if decision.confidence < self.confidence_threshold:
            flags.append("low_confidence")

        rules_of_engagement = str(decision.context.get("rules_of_engagement", "")).lower()
        if decision.decision_type == DecisionType.ENGAGE and rules_of_engagement == "weapons_hold":
            flags.append("roe_violation_weapons_hold")
            approved = False
            reason = "Blocked: engagement under weapons_hold is not authorized."

        if decision.decision_type == DecisionType.STRIKE:
            flags.append("strike_requires_human_review")
            approved = False
            reason = "Blocked pending review: strike decisions always require human authorization."

        llm_uncertain = bool(
            decision.llm_consulted
            and (
                decision.context.get("llm_uncertain") is True
                or "uncertain" in str(decision.context.get("llm_response", "")).lower()
            )
        )
        if llm_uncertain:
            flags.append("llm_uncertain_guidance")

        requires_review = bool(flags) and approved
        if decision.decision_type == DecisionType.STRIKE:
            requires_review = True
        if not approved:
            requires_review = True

        if requires_review:
            decision.requires_human_review = True
            self._review_queue[decision.decision_id] = decision
            if approved:
                reason = "Decision requires human review due to assurance flags."

        return {
            "approved": approved,
            "flags": flags,
            "requires_human_review": requires_review,
            "reason": reason,
        }

    def check_batch(self, decisions: List[AutonomyDecision]) -> Dict[str, object]:
        """Assess a decision batch and summarize assurance outcomes."""
        results = [self.check(decision) for decision in decisions]
        approved_count = sum(1 for result in results if bool(result["approved"]))
        review_count = sum(1 for result in results if bool(result["requires_human_review"]))
        return {
            "total": len(decisions),
            "approved": approved_count,
            "requires_human_review": review_count,
            "results": results,
        }

    def get_review_queue(self) -> List[AutonomyDecision]:
        """Return all decisions awaiting human review."""
        return list(self._review_queue.values())

    def approve(self, decision_id: str, reviewer: str) -> None:
        """Mark review-queued decision as human-approved."""
        decision = self._review_queue.pop(decision_id, None)
        if decision is None:
            raise KeyError(f"decision not in review queue: {decision_id}")
        decision.requires_human_review = False
        self._history[decision_id] = _ReviewRecord(
            decision_id=decision_id,
            reviewer=reviewer,
            approved=True,
            reason="approved",
        )

    def reject(self, decision_id: str, reviewer: str, reason: str) -> None:
        """Mark review-queued decision as rejected with justification."""
        decision = self._review_queue.pop(decision_id, None)
        if decision is None:
            raise KeyError(f"decision not in review queue: {decision_id}")
        decision.requires_human_review = True
        self._history[decision_id] = _ReviewRecord(
            decision_id=decision_id,
            reviewer=reviewer,
            approved=False,
            reason=reason,
        )
