"""Unit tests for the probabilistic decision engine package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.decision import (
    ActionType,
    DecisionOption,
    DecisionRecord,
    ObjectiveWeights,
    ProbabilisticDecisionEngine,
    ROEConstraint,
    ROELevel,
    ScoringContext,
)


@dataclass(frozen=True)
class _DummyDoctrineContext:
    escalation_level: int = 2
    engagement_auth: str = "HITL"


class _DummyBeliefState:
    def __init__(
        self,
        state_id: str,
        confidence_distribution: dict[str, float],
        entropy_value: float,
        doctrine_context: _DummyDoctrineContext | None = None,
    ) -> None:
        self.state_id = state_id
        self.confidence_distribution = confidence_distribution
        self._entropy_value = entropy_value
        self.doctrine_context = doctrine_context or _DummyDoctrineContext()

    def entropy(self) -> float:
        return self._entropy_value


def _make_option(
    label: str,
    action_type: ActionType = ActionType.HOLD,
    expected_outcome: float = 0.7,
    probability_of_success: float = 0.7,
    risk_score: float = 0.2,
    cost_score: float = 0.2,
    uncertainty: float = 0.2,
) -> DecisionOption:
    return DecisionOption(
        label=label,
        action_type=action_type,
        expected_outcome=expected_outcome,
        probability_of_success=probability_of_success,
        risk_score=risk_score,
        cost_score=cost_score,
        uncertainty=uncertainty,
    )


class TestDecisionOption:
    def test_auto_uuid(self) -> None:
        option = _make_option("Alpha")
        assert option.option_id
        assert isinstance(option.option_id, str)

    def test_blank_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_option("   ")

    def test_scores_bounded(self) -> None:
        with pytest.raises(ValidationError):
            _make_option("A", expected_outcome=1.1)
        with pytest.raises(ValidationError):
            _make_option("B", probability_of_success=-0.1)
        with pytest.raises(ValidationError):
            _make_option("C", risk_score=2.0)
        with pytest.raises(ValidationError):
            _make_option("D", cost_score=-1.0)
        with pytest.raises(ValidationError):
            _make_option("E", uncertainty=1.5)

    def test_raw_expected_value(self) -> None:
        option = _make_option("Alpha", expected_outcome=0.8, probability_of_success=0.5)
        assert option.raw_expected_value == pytest.approx(0.4)

    def test_arabic_label_optional(self) -> None:
        option = DecisionOption(
            label="Recon Sweep",
            label_ar="استطلاع",
            expected_outcome=0.6,
            probability_of_success=0.8,
            risk_score=0.1,
            cost_score=0.2,
            uncertainty=0.3,
        )
        assert option.label_ar == "استطلاع"

    def test_frozen(self) -> None:
        option = _make_option("Frozen")
        with pytest.raises(ValidationError):
            option.label = "Mutated"


class TestObjectiveWeights:
    def test_default_weights_sum_to_one(self) -> None:
        weights = ObjectiveWeights()
        total = (
            weights.outcome_weight
            + weights.success_weight
            + weights.risk_weight
            + weights.cost_weight
            + weights.uncertainty_weight
        )
        assert total == pytest.approx(1.0, abs=0.001)

    def test_balanced_weights_each_020(self) -> None:
        weights = ObjectiveWeights.balanced()
        assert weights.outcome_weight == pytest.approx(0.2)
        assert weights.success_weight == pytest.approx(0.2)
        assert weights.risk_weight == pytest.approx(0.2)
        assert weights.cost_weight == pytest.approx(0.2)
        assert weights.uncertainty_weight == pytest.approx(0.2)

    def test_risk_averse_risk_weight_highest(self) -> None:
        weights = ObjectiveWeights.risk_averse()
        assert weights.risk_weight > weights.outcome_weight
        assert weights.risk_weight > weights.success_weight
        assert weights.risk_weight > weights.cost_weight
        assert weights.risk_weight > weights.uncertainty_weight

    def test_mission_focused_outcome_weight_highest(self) -> None:
        weights = ObjectiveWeights.mission_focused()
        assert weights.outcome_weight > weights.success_weight
        assert weights.outcome_weight > weights.risk_weight
        assert weights.outcome_weight > weights.cost_weight
        assert weights.outcome_weight > weights.uncertainty_weight

    def test_invalid_weights_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ObjectiveWeights(
                outcome_weight=0.1,
                success_weight=0.1,
                risk_weight=0.1,
                cost_weight=0.1,
                uncertainty_weight=0.1,
            )

    def test_custom_valid_weights_accepted(self) -> None:
        weights = ObjectiveWeights(
            outcome_weight=0.3,
            success_weight=0.3,
            risk_weight=0.2,
            cost_weight=0.1,
            uncertainty_weight=0.1,
        )
        assert weights.outcome_weight == pytest.approx(0.3)


class TestROEConstraint:
    def test_default_factory(self) -> None:
        roe = ROEConstraint.default()
        assert roe.roe_level == ROELevel.WEAPONS_TIGHT

    def test_prohibited_action_blocks_engage(self) -> None:
        roe = ROEConstraint(
            roe_level=ROELevel.WEAPONS_TIGHT,
            prohibited_action_types=[ActionType.ENGAGE],
        )
        engine = ProbabilisticDecisionEngine(roe=roe)
        result = engine.evaluate(
            [
                _make_option("Forbidden", action_type=ActionType.ENGAGE),
                _make_option("Allowed", action_type=ActionType.HOLD),
            ]
        )
        blocked = next(
            item for item in result.result.all_options() if item.option.label == "Forbidden"
        )
        assert blocked.roe_vetoed is True

    def test_max_engagement_prob_at_zero_blocks_all_risky(self) -> None:
        roe = ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.0)
        engine = ProbabilisticDecisionEngine(roe=roe)
        with pytest.raises(ValueError, match="All options vetoed"):
            engine.evaluate([_make_option("Risky", risk_score=0.1)])

    def test_weapons_hold_level(self) -> None:
        roe = ROEConstraint(roe_level=ROELevel.WEAPONS_HOLD)
        assert roe.roe_level == ROELevel.WEAPONS_HOLD

    def test_frozen(self) -> None:
        roe = ROEConstraint.default()
        with pytest.raises(ValidationError):
            roe.max_engagement_prob = 0.2


class TestScoringContext:
    def test_defaults_valid(self) -> None:
        context = ScoringContext(weights=ObjectiveWeights(), roe=ROEConstraint.default())
        assert context.belief_entropy == pytest.approx(0.0)
        assert context.leading_hypothesis_confidence == pytest.approx(0.5)
        assert context.mission_phase == "UNKNOWN"

    def test_with_high_entropy(self) -> None:
        context = ScoringContext(
            weights=ObjectiveWeights(),
            roe=ROEConstraint.default(),
            belief_entropy=3.0,
        )
        assert context.belief_entropy == pytest.approx(3.0)

    def test_frozen(self) -> None:
        context = ScoringContext(weights=ObjectiveWeights(), roe=ROEConstraint.default())
        with pytest.raises(ValidationError):
            context.mission_phase = "PHASE_2"


class TestProbabilisticDecisionEngineHigherEV:
    def test_higher_ev_option_selected(self) -> None:
        engine = ProbabilisticDecisionEngine()
        a = _make_option("A", expected_outcome=0.9, probability_of_success=0.9)
        b = _make_option("B", expected_outcome=0.3, probability_of_success=0.3)
        result = engine.evaluate([a, b])
        assert result.result.selected.option.label == "A"

    def test_equal_options_highest_utility_selected(self) -> None:
        engine = ProbabilisticDecisionEngine()
        a = _make_option("A", expected_outcome=0.7, probability_of_success=0.7)
        b = _make_option("B", expected_outcome=0.7, probability_of_success=0.7)
        result = engine.evaluate([a, b])
        assert result.result.selected.utility_score == pytest.approx(
            max(item.utility_score for item in result.result.all_options())
        )

    def test_empty_options_raises_valueerror(self) -> None:
        engine = ProbabilisticDecisionEngine()
        with pytest.raises(ValueError):
            engine.evaluate([])

    def test_single_option_is_selected(self) -> None:
        engine = ProbabilisticDecisionEngine()
        only = _make_option("Only")
        result = engine.evaluate([only])
        assert result.result.selected.option.label == "Only"
        assert result.result.alternatives == []

    def test_utility_score_in_range(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate(
            [
                _make_option(
                    "Bounded",
                    expected_outcome=1.0,
                    probability_of_success=1.0,
                    risk_score=0.0,
                    cost_score=0.0,
                    uncertainty=0.0,
                )
            ]
        )
        assert -1.0 <= result.result.selected.utility_score <= 1.0

    def test_selected_has_rank_one(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("A"), _make_option("B", expected_outcome=0.3)])
        assert result.result.selected.rank == 1

    def test_alternatives_sorted_by_rank(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate(
            [
                _make_option("A", expected_outcome=0.9),
                _make_option("B", expected_outcome=0.6),
                _make_option("C", expected_outcome=0.2),
            ]
        )
        ranks = [item.rank for item in result.result.alternatives]
        assert ranks == sorted(ranks)

    def test_all_options_covered_in_result(self) -> None:
        engine = ProbabilisticDecisionEngine()
        options = [_make_option("A"), _make_option("B"), _make_option("C")]
        result = engine.evaluate(options)
        assert len(result.result.all_options()) == len(options)


class TestProbabilisticDecisionEngineUncertainty:
    def test_high_uncertainty_reduces_utility(self) -> None:
        engine = ProbabilisticDecisionEngine()
        low_u = _make_option("LowU", uncertainty=0.1)
        high_u = _make_option("HighU", uncertainty=0.9)
        result = engine.evaluate([low_u, high_u])
        scored = {item.option.label: item for item in result.result.all_options()}
        assert scored["LowU"].utility_score > scored["HighU"].utility_score

    def test_uncertainty_reduces_confidence(self) -> None:
        engine = ProbabilisticDecisionEngine()
        low = engine.evaluate([_make_option("Low", uncertainty=0.1)])
        high = engine.evaluate([_make_option("High", uncertainty=0.9)])
        assert low.result.confidence > high.result.confidence

    def test_uncertainty_exponent_convex(self) -> None:
        engine = ProbabilisticDecisionEngine(
            weights=ObjectiveWeights.balanced(),
            uncertainty_exponent=2.0,
        )
        low = _make_option("U45", uncertainty=0.45)
        high = _make_option("U90", uncertainty=0.9)
        result = engine.evaluate([low, high])
        penalties = {item.option.label: item.uncertainty_penalty for item in result.result.all_options()}
        assert penalties["U90"] > 2.0 * penalties["U45"]


class TestProbabilisticDecisionEngineROEVetoes:
    def test_prohibited_action_type_vetoed(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(
                roe_level=ROELevel.WEAPONS_TIGHT,
                prohibited_action_types=[ActionType.ENGAGE],
            )
        )
        result = engine.evaluate([_make_option("E", action_type=ActionType.ENGAGE), _make_option("H")])
        vetoed = next(item for item in result.result.all_options() if item.option.label == "E")
        assert vetoed.roe_vetoed is True

    def test_risk_above_threshold_vetoed(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.4)
        )
        result = engine.evaluate(
            [_make_option("Risky", risk_score=0.8), _make_option("Safe", risk_score=0.2)]
        )
        risky = next(item for item in result.result.all_options() if item.option.label == "Risky")
        assert risky.roe_vetoed is True

    def test_vetoed_option_not_selected(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.4)
        )
        result = engine.evaluate(
            [_make_option("Risky", risk_score=0.8), _make_option("Safe", risk_score=0.1)]
        )
        assert result.result.selected.option.label == "Safe"

    def test_all_vetoed_raises_valueerror(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.2)
        )
        with pytest.raises(ValueError, match="All options vetoed by ROE constraints"):
            engine.evaluate(
                [_make_option("RiskyA", risk_score=0.9), _make_option("RiskyB", risk_score=0.8)]
            )

    def test_veto_reason_populated(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.4)
        )
        result = engine.evaluate(
            [_make_option("Risky", risk_score=0.8), _make_option("Safe", risk_score=0.2)]
        )
        risky = next(item for item in result.result.all_options() if item.option.label == "Risky")
        assert risky.veto_reason

    def test_veto_reason_ar_populated(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(roe_level=ROELevel.WEAPONS_TIGHT, max_engagement_prob=0.4)
        )
        result = engine.evaluate(
            [_make_option("Risky", risk_score=0.8), _make_option("Safe", risk_score=0.2)]
        )
        risky = next(item for item in result.result.all_options() if item.option.label == "Risky")
        assert risky.veto_reason_ar

    def test_high_risk_flags_human_review(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(
                roe_level=ROELevel.WEAPONS_TIGHT,
                max_engagement_prob=1.0,
                require_human_review_above_risk=0.8,
            )
        )
        result = engine.evaluate([_make_option("HighRisk", risk_score=0.95)])
        assert result.result.requires_human_review is True

    def test_low_risk_no_human_review(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(
                roe_level=ROELevel.WEAPONS_TIGHT,
                max_engagement_prob=1.0,
                require_human_review_above_risk=0.8,
            )
        )
        result = engine.evaluate([_make_option("LowRisk", risk_score=0.2)])
        assert result.result.requires_human_review is False


class TestProbabilisticDecisionEngineRationale:
    def test_rationale_en_is_nonempty_string(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        assert isinstance(result.result.rationale, str)
        assert result.result.rationale.strip()

    def test_rationale_ar_is_nonempty_string(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        assert isinstance(result.result.rationale_ar, str)
        assert result.result.rationale_ar.strip()

    def test_rationale_mentions_selected_label(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("NamedOption")])
        assert "NamedOption" in result.result.rationale

    def test_rationale_mentions_confidence(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        assert "confidence" in result.result.rationale.lower()

    def test_rationale_mentions_alternatives_count(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("A"), _make_option("B")])
        assert "Alternatives considered: 1" in result.result.rationale

    def test_scoring_breakdown_all_keys_present(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        keys = set(result.result.scoring_breakdown.keys())
        assert keys == {
            "ev_component",
            "risk_penalty",
            "cost_penalty",
            "uncertainty_penalty",
            "utility_score",
            "confidence",
        }

    def test_computation_ms_positive(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        assert result.computation_ms > 0.0


class TestProbabilisticDecisionEngineBeliefStateIntegration:
    def test_evaluates_with_belief_state(self) -> None:
        engine = ProbabilisticDecisionEngine()
        belief = _DummyBeliefState(
            state_id="belief-1",
            confidence_distribution={"h1": 0.9},
            entropy_value=0.2,
        )
        result = engine.evaluate([_make_option("Alpha")], belief_state=belief)
        assert isinstance(result, DecisionRecord)

    def test_belief_entropy_affects_confidence(self) -> None:
        engine = ProbabilisticDecisionEngine()
        low_entropy = _DummyBeliefState(
            state_id="low",
            confidence_distribution={"h1": 0.8},
            entropy_value=0.0,
        )
        high_entropy = _DummyBeliefState(
            state_id="high",
            confidence_distribution={"h1": 0.8},
            entropy_value=5.0,
        )
        low = engine.evaluate([_make_option("Alpha")], belief_state=low_entropy)
        high = engine.evaluate([_make_option("Alpha")], belief_state=high_entropy)
        assert low.result.confidence > high.result.confidence

    def test_belief_snapshot_id_set_when_state_provided(self) -> None:
        engine = ProbabilisticDecisionEngine()
        belief = _DummyBeliefState(
            state_id="belief-id",
            confidence_distribution={"h1": 0.7},
            entropy_value=0.3,
        )
        result = engine.evaluate([_make_option("Alpha")], belief_state=belief)
        assert result.result.belief_snapshot_id == "belief-id"

    def test_belief_snapshot_id_none_when_no_state(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("Alpha")])
        assert result.result.belief_snapshot_id is None


class TestDecisionRecord:
    def test_all_options_returns_selected_plus_alternatives(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("A"), _make_option("B"), _make_option("C")])
        all_options = result.result.all_options()
        assert len(all_options) == 3
        assert all_options[0].rank == 1

    def test_was_vetoed_true_for_vetoed_id(self) -> None:
        engine = ProbabilisticDecisionEngine(
            roe=ROEConstraint(
                roe_level=ROELevel.WEAPONS_TIGHT,
                prohibited_action_types=[ActionType.ENGAGE],
            )
        )
        result = engine.evaluate([_make_option("E", action_type=ActionType.ENGAGE), _make_option("H")])
        vetoed = next(item for item in result.result.all_options() if item.option.label == "E")
        assert result.result.was_vetoed(vetoed.option.option_id) is True

    def test_was_vetoed_false_for_selected_id(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("A"), _make_option("B", expected_outcome=0.4)])
        assert result.result.was_vetoed(result.result.selected.option.option_id) is False

    def test_frozen(self) -> None:
        engine = ProbabilisticDecisionEngine()
        result = engine.evaluate([_make_option("A")])
        with pytest.raises(ValidationError):
            result.options_evaluated = 99


class TestObjectiveWeightsIntegration:
    def test_risk_averse_weights_prefer_safe_option(self) -> None:
        engine = ProbabilisticDecisionEngine(weights=ObjectiveWeights.risk_averse())
        safe = _make_option("Safe", risk_score=0.1, expected_outcome=0.7, probability_of_success=0.7)
        risky = _make_option("Risky", risk_score=0.8, expected_outcome=0.9, probability_of_success=0.7)
        result = engine.evaluate([safe, risky])
        assert result.result.selected.option.label == "Safe"

    def test_mission_focused_weights_prefer_high_outcome(self) -> None:
        engine = ProbabilisticDecisionEngine(weights=ObjectiveWeights.mission_focused())
        high_outcome = _make_option(
            "HighOutcome",
            expected_outcome=0.95,
            probability_of_success=0.8,
            risk_score=0.6,
            cost_score=0.1,
            uncertainty=0.1,
        )
        low_outcome = _make_option(
            "LowOutcome",
            expected_outcome=0.4,
            probability_of_success=0.8,
            risk_score=0.1,
            cost_score=0.1,
            uncertainty=0.1,
        )
        result = engine.evaluate([high_outcome, low_outcome])
        assert result.result.selected.option.label == "HighOutcome"
