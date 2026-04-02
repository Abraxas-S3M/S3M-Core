"""Probabilistic decision engine for tactical option scoring."""

from __future__ import annotations

import math
import time
from typing import Any, List, Optional, Tuple, TYPE_CHECKING

from .decision_models import (
    DecisionOption,
    DecisionRecord,
    DecisionResult,
    ObjectiveWeights,
    ROEConstraint,
    ROELevel,
    ScoredOption,
    ScoringContext,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.belief_state.models import BeliefState, DoctrineContext, MissionPhase
else:  # pragma: no cover - runtime compatibility when module is absent
    BeliefState = Any


class ProbabilisticDecisionEngine:
    """Numerically scores options under uncertainty and ROE constraints."""

    def __init__(
        self,
        weights: ObjectiveWeights = None,
        roe: ROEConstraint = None,
        uncertainty_exponent: float = 2.0,
        min_options: int = 1,
    ) -> None:
        """Initialize the tactical scoring engine configuration."""
        self._weights = weights if weights is not None else ObjectiveWeights.balanced()
        self._roe = roe if roe is not None else ROEConstraint.default()
        self._uncertainty_exponent = float(uncertainty_exponent)
        self._min_options = int(min_options)

    def evaluate(
        self,
        options: List[DecisionOption],
        belief_state: Optional[BeliefState] = None,
        author_id: Optional[str] = None,
    ) -> DecisionRecord:
        """Evaluate decision options and return an auditable decision record."""
        start = time.perf_counter()
        if not options:
            raise ValueError("options is empty")
        if len(options) < self._min_options:
            raise ValueError("Number of options is below min_options")

        belief_entropy = 0.0
        leading_hypothesis_confidence = 0.5
        mission_phase = "UNKNOWN"
        active_roe = self._roe

        if belief_state is not None:
            belief_entropy = float(getattr(belief_state, "entropy")())
            distribution = getattr(belief_state, "confidence_distribution", {})
            if isinstance(distribution, dict):
                leading_hypothesis_confidence = float(max(distribution.values(), default=0.5))

            doctrine_context = getattr(belief_state, "doctrine_context", None)
            escalation_level = getattr(doctrine_context, "escalation_level", "UNKNOWN")
            mission_phase = str(escalation_level)

            engagement_auth = getattr(doctrine_context, "engagement_auth", None)
            if engagement_auth == "HITL":
                merged_roe_level = ROELevel.WEAPONS_TIGHT
            elif engagement_auth == "HOTL":
                merged_roe_level = ROELevel.WEAPONS_FREE
            else:
                merged_roe_level = self._roe.roe_level
            active_roe = self._roe.model_copy(update={"roe_level": merged_roe_level})

        context = ScoringContext(
            weights=self._weights,
            roe=active_roe,
            belief_entropy=belief_entropy,
            leading_hypothesis_confidence=leading_hypothesis_confidence,
            mission_phase=mission_phase,
            author_id=author_id,
        )

        scored_options = [
            self._score_option(option, context.weights, context.roe, self._uncertainty_exponent)
            for option in options
        ]
        ranked = self._rank(scored_options)

        selected = next((candidate for candidate in ranked if not candidate.roe_vetoed), None)
        if selected is None:
            raise ValueError("All options vetoed by ROE constraints")
        selected_index = ranked.index(selected)
        alternatives = ranked[:selected_index] + ranked[selected_index + 1 :]
        vetoed_count = sum(1 for option in ranked if option.roe_vetoed)

        confidence = self._compute_confidence(selected, context)
        rationale_en = self._rationale_en(selected, alternatives, vetoed_count, confidence)
        rationale_ar = self._rationale_ar(selected, alternatives, vetoed_count, confidence)

        scoring_breakdown = {
            "ev_component": selected.ev_component,
            "risk_penalty": selected.risk_penalty,
            "cost_penalty": selected.cost_penalty,
            "uncertainty_penalty": selected.uncertainty_penalty,
            "utility_score": selected.utility_score,
            "confidence": confidence,
        }
        decision_result = DecisionResult(
            selected=selected,
            alternatives=alternatives,
            confidence=confidence,
            rationale=rationale_en,
            rationale_ar=rationale_ar,
            requires_human_review=selected.requires_human_review,
            belief_snapshot_id=getattr(belief_state, "state_id", None) if belief_state else None,
            scoring_breakdown=scoring_breakdown,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return DecisionRecord(
            result=decision_result,
            context=context,
            options_evaluated=len(options),
            options_vetoed=vetoed_count,
            computation_ms=max(elapsed_ms, 0.000001),
        )

    def _score_option(
        self,
        option: DecisionOption,
        weights: ObjectiveWeights,
        roe: ROEConstraint,
        uncertainty_exponent: float,
    ) -> ScoredOption:
        """Score one tactical option with ROE and uncertainty penalties."""
        vetoed, veto_reason_en, veto_reason_ar = self._veto_check(option, roe)
        requires_human_review = option.risk_score > roe.require_human_review_above_risk
        if vetoed:
            return ScoredOption(
                option=option,
                utility_score=float("-inf"),
                ev_component=0.0,
                risk_penalty=0.0,
                cost_penalty=0.0,
                uncertainty_penalty=0.0,
                roe_vetoed=True,
                veto_reason=veto_reason_en,
                veto_reason_ar=veto_reason_ar,
                requires_human_review=requires_human_review,
            )

        ev_component = (
            weights.outcome_weight * option.expected_outcome
            + weights.success_weight * option.probability_of_success
        )
        risk_penalty = weights.risk_weight * option.risk_score
        cost_penalty = weights.cost_weight * option.cost_score
        uncertainty_penalty = (
            weights.uncertainty_weight * (option.uncertainty ** uncertainty_exponent)
        )
        utility_score = ev_component - risk_penalty - cost_penalty - uncertainty_penalty
        utility_score = max(-1.0, min(1.0, utility_score))

        return ScoredOption(
            option=option,
            utility_score=utility_score,
            ev_component=ev_component,
            risk_penalty=risk_penalty,
            cost_penalty=cost_penalty,
            uncertainty_penalty=uncertainty_penalty,
            roe_vetoed=False,
            veto_reason=None,
            veto_reason_ar=None,
            requires_human_review=requires_human_review,
        )

    def _veto_check(
        self, option: DecisionOption, roe: ROEConstraint
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Apply ROE veto checks before utility scoring."""
        if option.action_type in roe.prohibited_action_types:
            return (
                True,
                f"Action type {option.action_type.value} is prohibited by current ROE.",
                f"نوع الإجراء {option.action_type.value} محظور وفق قواعد الاشتباك الحالية.",
            )
        if option.risk_score > roe.max_engagement_prob:
            return (
                True,
                (
                    f"Risk score {option.risk_score:.2f} exceeds allowed engagement threshold "
                    f"{roe.max_engagement_prob:.2f}."
                ),
                (
                    f"درجة المخاطر {option.risk_score:.2f} تتجاوز حد الاشتباك المسموح "
                    f"{roe.max_engagement_prob:.2f}."
                ),
            )
        return False, None, None

    def _rank(self, scored_options: List[ScoredOption]) -> List[ScoredOption]:
        """Rank options with non-vetoed scores first and vetoed scores last."""
        ordered = sorted(
            scored_options,
            key=lambda item: (
                1 if item.roe_vetoed else 0,
                -item.utility_score if not item.roe_vetoed else 0.0,
            ),
        )
        return [
            candidate.model_copy(update={"rank": index})
            for index, candidate in enumerate(ordered, start=1)
        ]

    def _compute_confidence(self, selected: ScoredOption, context: ScoringContext) -> float:
        """Compute confidence from belief concentration and selected option quality."""
        confidence = (
            context.leading_hypothesis_confidence * selected.option.probability_of_success
        )
        confidence *= math.exp(-0.1 * context.belief_entropy)
        confidence *= 1.0 - (selected.option.uncertainty * 0.5)
        return max(0.0, min(1.0, confidence))

    def _rationale_en(
        self,
        selected: ScoredOption,
        alternatives: List[ScoredOption],
        vetoed_count: int,
        confidence: float,
    ) -> str:
        """Generate deterministic English rationale for tactical audit trails."""
        review_note = (
            " Human review is required due to elevated risk."
            if selected.requires_human_review
            else ""
        )
        return (
            f"Selected option '{selected.option.label}' ({selected.option.action_type.value}) "
            f"with utility score {selected.utility_score:.4f}. "
            f"EV component={selected.ev_component:.4f}, "
            f"risk penalty={selected.risk_penalty:.4f}, "
            f"uncertainty penalty={selected.uncertainty_penalty:.4f}. "
            f"Alternatives considered: {len(alternatives)}; vetoed options: {vetoed_count}. "
            f"Confidence={confidence:.4f}.{review_note}"
        )

    def _rationale_ar(
        self,
        selected: ScoredOption,
        alternatives: List[ScoredOption],
        vetoed_count: int,
        confidence: float,
    ) -> str:
        """Generate deterministic Arabic rationale for bilingual operator review."""
        review_note = (
            " يلزم اعتماد بشري بسبب ارتفاع مستوى المخاطر."
            if selected.requires_human_review
            else ""
        )
        return (
            f"تم اختيار الخيار '{selected.option.label}' ({selected.option.action_type.value}) "
            f"بدرجة منفعة {selected.utility_score:.4f}. "
            f"مكوّن القيمة المتوقعة={selected.ev_component:.4f}، "
            f"خصم المخاطر={selected.risk_penalty:.4f}، "
            f"خصم عدم اليقين={selected.uncertainty_penalty:.4f}. "
            f"عدد البدائل التي تم تقييمها: {len(alternatives)}، "
            f"وعدد الخيارات المحجوبة بقواعد الاشتباك: {vetoed_count}. "
            f"مستوى الثقة={confidence:.4f}.{review_note}"
        )
