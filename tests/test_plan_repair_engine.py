from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.replanning import (
    BeliefShiftReport,
    BranchGeneratorConfig,
    EvaluatorWeights,
    MissionPlan,
    PlanBranch,
    PlanRepairEngine,
    PlanStatus,
    PlanStep,
    RepairTrigger,
    StepType,
)
from src.replanning.plan_repair_engine import (
    BeliefShiftDetector,
    BranchEvaluator,
    BranchGenerator,
)


def _step(
    label: str = "Step-A",
    step_type: StepType = StepType.MOVE,
    success: float = 0.8,
    risk: float = 0.2,
    cost: float = 0.1,
) -> PlanStep:
    return PlanStep(
        label=label,
        step_type=step_type,
        expected_success_prob=success,
        risk_score=risk,
        cost_score=cost,
    )


def _plan(
    n_steps: int = 3,
    expected_dist: dict[str, float] | None = None,
    completion: float = 0.8,
    outcome: float = 0.8,
    risk: float = 0.2,
) -> MissionPlan:
    steps = [_step(label=f"Step-{i + 1}") for i in range(n_steps)]
    return MissionPlan(
        label="Base Mission",
        label_ar="مهمة أساسية",
        steps=steps,
        expected_belief_distribution=expected_dist or {},
        expected_completion_prob=completion,
        expected_outcome=outcome,
        overall_risk=risk,
    )


def _uniform_dist(n: int = 3) -> dict[str, float]:
    value = 1.0 / n
    return {f"h{i}": value for i in range(n)}


def _shifted_dist(n: int = 3, dominant_idx: int = 0, dominant_p: float = 0.9) -> dict[str, float]:
    dist = {f"h{i}": 0.0 for i in range(n)}
    if n == 1:
        dist["h0"] = 1.0
        return dist
    remainder = (1.0 - dominant_p) / (n - 1)
    for i in range(n):
        dist[f"h{i}"] = dominant_p if i == dominant_idx else remainder
    return dist


def _engine(**kwargs) -> PlanRepairEngine:
    return PlanRepairEngine(**kwargs)


def _report(
    plan_status: PlanStatus = PlanStatus.DEGRADED,
    entropy_actual: float = 1.0,
    triggers: list[RepairTrigger] | None = None,
) -> BeliefShiftReport:
    return BeliefShiftReport(
        js_divergence=0.3,
        kl_divergence_fwd=0.1,
        entropy_actual=entropy_actual,
        entropy_expected=0.8,
        entropy_delta=0.2,
        leading_confidence=0.5,
        shift_magnitude=0.25,
        triggers=triggers or [RepairTrigger.BELIEF_SHIFT],
        plan_status=plan_status,
    )


class TestPlanStep:
    def test_auto_uuid(self):
        step = _step()
        assert isinstance(step.step_id, str)
        assert step.step_id

    def test_blank_label_rejected(self):
        with pytest.raises(ValidationError):
            PlanStep(label="   ")

    def test_scores_bounded(self):
        step = _step(success=0.6, risk=0.4, cost=0.3)
        assert 0.0 <= step.expected_success_prob <= 1.0
        assert 0.0 <= step.risk_score <= 1.0
        assert 0.0 <= step.cost_score <= 1.0

    def test_frozen(self):
        step = _step()
        with pytest.raises(ValidationError):
            step.label = "Changed"


class TestMissionPlan:
    def test_auto_uuid(self):
        plan = _plan()
        assert isinstance(plan.plan_id, str)
        assert plan.plan_id

    def test_requires_at_least_one_step(self):
        with pytest.raises(ValidationError):
            MissionPlan(label="Invalid", steps=[])

    def test_total_duration_sum(self):
        steps = [
            PlanStep(label="A", expected_duration_s=10.0),
            PlanStep(label="B", expected_duration_s=20.5),
        ]
        plan = MissionPlan(label="Dur", steps=steps)
        assert plan.total_expected_duration_s() == pytest.approx(30.5)

    def test_average_step_risk(self):
        steps = [_step(label="A", risk=0.1), _step(label="B", risk=0.5)]
        plan = MissionPlan(label="Risk", steps=steps)
        assert plan.average_step_risk() == pytest.approx(0.3)

    def test_age_seconds_fresh(self):
        plan = _plan()
        assert plan.age_seconds() < 2.0

    def test_invalid_expected_dist_rejected(self):
        with pytest.raises(ValidationError):
            _plan(expected_dist={"a": 0.2, "b": 0.2})

    def test_frozen(self):
        plan = _plan()
        with pytest.raises(ValidationError):
            plan.label = "Mutated"


class TestEvaluatorWeights:
    def test_default_weights_sum_to_one(self):
        w = EvaluatorWeights()
        total = (
            w.outcome_weight
            + w.success_weight
            + w.risk_weight
            + w.cost_weight
            + w.uncertainty_weight
            + w.divergence_weight
        )
        assert total == pytest.approx(1.0, abs=0.001)

    def test_conservative_risk_weight_highest(self):
        w = EvaluatorWeights.conservative()
        assert w.risk_weight == max(
            w.outcome_weight,
            w.success_weight,
            w.risk_weight,
            w.cost_weight,
            w.uncertainty_weight,
            w.divergence_weight,
        )

    def test_aggressive_outcome_weight_highest(self):
        w = EvaluatorWeights.aggressive()
        assert w.outcome_weight == max(
            w.outcome_weight,
            w.success_weight,
            w.risk_weight,
            w.cost_weight,
            w.uncertainty_weight,
            w.divergence_weight,
        )

    def test_invalid_sum_rejected(self):
        with pytest.raises(ValidationError):
            EvaluatorWeights(
                outcome_weight=0.2,
                success_weight=0.2,
                risk_weight=0.2,
                cost_weight=0.2,
                uncertainty_weight=0.2,
                divergence_weight=0.2,
            )


class TestBeliefShiftDetector:
    def test_nominal_when_no_shift(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        detector = BeliefShiftDetector()
        report = detector.detect(
            plan=plan,
            actual_dist=_uniform_dist(3),
            actual_entropy=detector._entropy(_uniform_dist(3)),
            leading_confidence=0.4,
        )
        assert report.plan_status == PlanStatus.NOMINAL
        assert report.triggers == []

    def test_degraded_when_small_shift(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        detector = BeliefShiftDetector(shift_threshold=0.25, failure_threshold=0.5)
        actual = {"a": 0.3, "b": 0.7}
        report = detector.detect(
            plan=plan,
            actual_dist=actual,
            actual_entropy=detector._entropy(actual),
            leading_confidence=0.7,
        )
        assert 0.25 < report.js_divergence < 0.5
        assert report.plan_status == PlanStatus.DEGRADED

    def test_failed_when_large_shift(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        detector = BeliefShiftDetector()
        actual = {"a": 0.0, "b": 1.0}
        report = detector.detect(
            plan=plan,
            actual_dist=actual,
            actual_entropy=detector._entropy(actual),
            leading_confidence=1.0,
        )
        assert report.plan_status == PlanStatus.FAILED
        assert RepairTrigger.BELIEF_SHIFT in report.triggers

    def test_high_entropy_triggers_correctly(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        detector = BeliefShiftDetector(entropy_threshold=2.0)
        report = detector.detect(
            plan=plan,
            actual_dist=_uniform_dist(3),
            actual_entropy=3.0,
            leading_confidence=0.4,
        )
        assert RepairTrigger.HIGH_ENTROPY in report.triggers

    def test_low_confidence_triggers_correctly(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        detector = BeliefShiftDetector(confidence_threshold=0.35)
        report = detector.detect(
            plan=plan,
            actual_dist=_uniform_dist(3),
            actual_entropy=1.0,
            leading_confidence=0.2,
        )
        assert RepairTrigger.LOW_CONFIDENCE in report.triggers

    def test_plan_expired_trigger(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        detector = BeliefShiftDetector(max_plan_age_seconds=300.0)
        report = detector.detect(
            plan=plan,
            actual_dist=_uniform_dist(3),
            actual_entropy=1.0,
            leading_confidence=0.6,
            plan_age_seconds=400.0,
        )
        assert RepairTrigger.PLAN_EXPIRED in report.triggers

    def test_combined_trigger_when_multiple_active(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        detector = BeliefShiftDetector(entropy_threshold=0.2)
        actual = {"a": 0.0, "b": 1.0}
        report = detector.detect(
            plan=plan,
            actual_dist=actual,
            actual_entropy=1.0,
            leading_confidence=0.1,
        )
        assert report.triggers == [RepairTrigger.COMBINED]

    def test_repair_required_true_when_failed(self):
        report = _report(plan_status=PlanStatus.FAILED)
        assert report.repair_required() is True

    def test_repair_required_false_when_nominal(self):
        report = BeliefShiftReport(
            js_divergence=0.0,
            kl_divergence_fwd=0.0,
            entropy_actual=0.0,
            entropy_expected=0.0,
            entropy_delta=0.0,
            leading_confidence=1.0,
            shift_magnitude=0.0,
            triggers=[],
            plan_status=PlanStatus.NOMINAL,
        )
        assert report.repair_required() is False

    def test_js_divergence_range(self):
        detector = BeliefShiftDetector()
        plan = _plan(expected_dist={"a": 0.6, "b": 0.4})
        report = detector.detect(
            plan=plan,
            actual_dist={"a": 0.05, "b": 0.95},
            actual_entropy=0.3,
            leading_confidence=0.95,
        )
        assert 0.0 <= report.js_divergence <= 1.0

    def test_shift_magnitude_range(self):
        detector = BeliefShiftDetector()
        plan = _plan(expected_dist={"a": 0.5, "b": 0.5})
        report = detector.detect(
            plan=plan,
            actual_dist={"a": 0.99, "b": 0.01},
            actual_entropy=1.5,
            leading_confidence=0.99,
        )
        assert 0.0 <= report.shift_magnitude <= 1.0

    def test_empty_expected_dist_handled(self):
        detector = BeliefShiftDetector()
        plan = _plan(expected_dist=None)
        report = detector.detect(
            plan=plan,
            actual_dist={"a": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert report.js_divergence == 0.0


class TestBranchGenerator:
    def test_generates_n_branches(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branches = BranchGenerator().generate(plan, report, _uniform_dist(3))
        assert len(branches) == 5

    def test_custom_n_branches(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        cfg = BranchGeneratorConfig(n_branches=3)
        branches = BranchGenerator(cfg).generate(plan, report, _uniform_dist(3))
        assert len(branches) == 3

    def test_branches_are_distinct(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branches = BranchGenerator().generate(plan, report, _uniform_dist(3))
        probs = [b.probability_of_success for b in branches]
        assert len(set(probs)) > 1

    def test_branch_0_has_zero_divergence_cost(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branch = BranchGenerator().generate(plan, report, _uniform_dist(3))[0]
        assert branch.divergence_cost == pytest.approx(0.0, abs=1e-9)

    def test_last_branch_has_highest_divergence_cost(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branches = BranchGenerator().generate(plan, report, _uniform_dist(3))
        assert branches[-1].divergence_cost == max(b.divergence_cost for b in branches)

    def test_branch_probs_bounded(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branches = BranchGenerator().generate(plan, report, _uniform_dist(3))
        assert all(0.0 <= b.probability_of_success <= 1.0 for b in branches)

    def test_branch_risks_bounded(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branches = BranchGenerator().generate(plan, report, _uniform_dist(3))
        assert all(0.0 <= b.risk_score <= 1.0 for b in branches)

    def test_uncertainty_reflects_entropy(self):
        plan = _plan(expected_dist=_uniform_dist(4))
        low = _report(entropy_actual=0.2)
        high = _report(entropy_actual=2.0)
        gen = BranchGenerator()
        low_b = gen.generate(plan, low, _uniform_dist(4))[0]
        high_b = gen.generate(plan, high, _uniform_dist(4))[0]
        assert high_b.uncertainty > low_b.uncertainty

    def test_label_contains_branch_number(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branch = BranchGenerator().generate(plan, report, _uniform_dist(3))[1]
        assert "Branch-2" in branch.label

    def test_label_ar_is_nonempty(self):
        plan = _plan(expected_dist=_uniform_dist(3))
        report = _report()
        branch = BranchGenerator().generate(plan, report, _uniform_dist(3))[0]
        assert isinstance(branch.label_ar, str) and branch.label_ar.strip()


class TestBranchEvaluator:
    def test_higher_ev_ranked_first(self):
        a = PlanBranch(
            label="A",
            label_ar="أ",
            steps=[_step()],
            expected_outcome=0.9,
            probability_of_success=0.9,
            risk_score=0.1,
            cost_score=0.1,
            uncertainty=0.1,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        b = PlanBranch(
            label="B",
            label_ar="ب",
            steps=[_step()],
            expected_outcome=0.3,
            probability_of_success=0.3,
            risk_score=0.8,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        scores = BranchEvaluator().score([a, b])
        assert scores[0].branch.label == "A"
        assert scores[0].rank == 1

    def test_high_uncertainty_reduces_utility(self):
        base_kwargs = dict(
            label_ar="X",
            steps=[_step()],
            expected_outcome=0.7,
            probability_of_success=0.7,
            risk_score=0.2,
            cost_score=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        a = PlanBranch(label="A", uncertainty=0.05, **base_kwargs)
        b = PlanBranch(label="B", uncertainty=0.90, **base_kwargs)
        scores = BranchEvaluator().score([a, b])
        util = {s.branch.label: s.utility for s in scores}
        assert util["A"] > util["B"]

    def test_utility_clamped(self):
        branch = PlanBranch(
            label="Extreme",
            label_ar="متطرف",
            steps=[_step()],
            expected_outcome=1.0,
            probability_of_success=1.0,
            risk_score=0.0,
            cost_score=0.0,
            uncertainty=0.0,
            divergence_cost=0.0,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        score = BranchEvaluator(
            weights=EvaluatorWeights(
                outcome_weight=0.5,
                success_weight=0.5,
                risk_weight=0.0,
                cost_weight=0.0,
                uncertainty_weight=0.0,
                divergence_weight=0.0,
            )
        ).score([branch])[0]
        assert -1.0 <= score.utility <= 1.0

    def test_rank_one_is_best_utility(self):
        a = PlanBranch(
            label="A",
            label_ar="أ",
            steps=[_step()],
            expected_outcome=0.8,
            probability_of_success=0.8,
            risk_score=0.2,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.2,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        b = PlanBranch(
            label="B",
            label_ar="ب",
            steps=[_step()],
            expected_outcome=0.4,
            probability_of_success=0.4,
            risk_score=0.7,
            cost_score=0.3,
            uncertainty=0.3,
            divergence_cost=0.2,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        scores = BranchEvaluator().score([a, b])
        assert scores[0].utility >= scores[1].utility
        assert scores[0].rank == 1

    def test_all_branches_appear_in_scores(self):
        branches = [
            PlanBranch(
                label=f"B{i}",
                label_ar=f"ف{i}",
                steps=[_step()],
                expected_outcome=0.7 - i * 0.1,
                probability_of_success=0.7 - i * 0.1,
                risk_score=0.2 + i * 0.1,
                cost_score=0.1,
                uncertainty=0.2,
                divergence_cost=0.1,
                generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
            )
            for i in range(3)
        ]
        scores = BranchEvaluator().score(branches)
        assert {s.branch.branch_id for s in scores} == {b.branch_id for b in branches}

    def test_divergence_penalty_applied(self):
        base_kwargs = dict(
            label_ar="X",
            steps=[_step()],
            expected_outcome=0.7,
            probability_of_success=0.7,
            risk_score=0.2,
            cost_score=0.2,
            uncertainty=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        low_div = PlanBranch(label="LowDiv", divergence_cost=0.0, **base_kwargs)
        high_div = PlanBranch(label="HighDiv", divergence_cost=1.0, **base_kwargs)
        scores = BranchEvaluator(max_divergence_penalty=0.3).score([high_div, low_div])
        util = {s.branch.label: s.utility for s in scores}
        assert util["LowDiv"] > util["HighDiv"]

    def test_conservative_weights_prefer_safe_branch(self):
        safe = PlanBranch(
            label="A",
            label_ar="أ",
            steps=[_step()],
            expected_outcome=0.6,
            probability_of_success=0.6,
            risk_score=0.1,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        risky = PlanBranch(
            label="B",
            label_ar="ب",
            steps=[_step()],
            expected_outcome=0.9,
            probability_of_success=0.6,
            risk_score=0.8,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        scores = BranchEvaluator(weights=EvaluatorWeights.conservative()).score([safe, risky])
        assert scores[0].branch.label == "A"

    def test_aggressive_weights_prefer_high_outcome_branch(self):
        safe = PlanBranch(
            label="A",
            label_ar="أ",
            steps=[_step()],
            expected_outcome=0.6,
            probability_of_success=0.7,
            risk_score=0.1,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        high = PlanBranch(
            label="B",
            label_ar="ب",
            steps=[_step()],
            expected_outcome=0.9,
            probability_of_success=0.7,
            risk_score=0.3,
            cost_score=0.2,
            uncertainty=0.2,
            divergence_cost=0.1,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        scores = BranchEvaluator(weights=EvaluatorWeights.aggressive()).score([safe, high])
        assert scores[0].branch.label == "B"


class TestPlanRepairEnginePlanChanges:
    def test_nominal_plan_returns_unchanged(self):
        expected = _uniform_dist(3)
        plan = _plan(expected_dist=expected)
        engine = _engine()
        entropy = BeliefShiftDetector()._entropy(expected)
        result = engine.evaluate(plan=plan, actual_dist=expected, actual_entropy=entropy, leading_confidence=0.4)
        assert result.repaired_plan.plan_id == plan.plan_id

    def test_failed_belief_triggers_repair(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        engine = _engine()
        result = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert result.repaired_plan.parent_plan_id == plan.plan_id

    def test_repaired_plan_version_incremented(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        engine = _engine()
        result = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert result.repaired_plan.version == plan.version + 1

    def test_repaired_plan_has_steps(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        engine = _engine()
        result = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert len(result.repaired_plan.steps) > 0

    def test_repair_result_computation_ms_positive(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        result = _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert result.computation_ms >= 0.0

    def test_shift_report_embedded_in_result(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        result = _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert isinstance(result.shift_report, BeliefShiftReport)


class TestPlanRepairEngineBetterPlan:
    def test_selected_branch_has_rank_one(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        result = _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert result.selected_branch.rank == 1

    def test_alternatives_sorted_by_rank(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        result = _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        ranks = [s.rank for s in result.alternative_branches]
        assert ranks == sorted(ranks)
        assert all(r >= 2 for r in ranks)

    def test_all_branches_in_result(self):
        cfg = BranchGeneratorConfig(n_branches=4)
        engine = _engine(branch_generator=BranchGenerator(cfg))
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0}, completion=0.4, outcome=0.4)
        result = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert len(result.all_branches()) == 4

    def test_improvement_computed(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        result = _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert isinstance(result.improvement(), float)

    def test_high_ev_branch_is_selected(self):
        class FixedGenerator(BranchGenerator):
            def generate(self, plan, shift_report, actual_dist):
                base_steps = [_step()]
                best = PlanBranch(
                    label="Best",
                    label_ar="الأفضل",
                    steps=base_steps,
                    expected_outcome=0.95,
                    probability_of_success=0.95,
                    risk_score=0.1,
                    cost_score=0.1,
                    uncertainty=0.05,
                    divergence_cost=0.1,
                    generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
                )
                weak = PlanBranch(
                    label="Weak",
                    label_ar="ضعيف",
                    steps=base_steps,
                    expected_outcome=0.2,
                    probability_of_success=0.2,
                    risk_score=0.7,
                    cost_score=0.5,
                    uncertainty=0.8,
                    divergence_cost=0.2,
                    generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
                )
                return [best, weak]

        engine = _engine(branch_generator=FixedGenerator())
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0}, completion=0.2, outcome=0.2)
        result = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )
        assert result.selected_branch.branch.label == "Best"


class TestPlanRepairEngineUncertainty:
    def test_high_entropy_increases_uncertainty_in_branches(self):
        plan = _plan(expected_dist=_uniform_dist(5))
        high_entropy_dist = _uniform_dist(5)
        high_entropy = BeliefShiftDetector()._entropy(high_entropy_dist)
        result = _engine().evaluate(
            plan=plan.model_copy(update={"expected_belief_distribution": {"a": 1.0, "b": 0.0}}),
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=high_entropy + 0.7,
            leading_confidence=0.25,
        )
        assert result.selected_branch.branch.uncertainty > 0.5

    def test_high_entropy_reduces_confidence(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        engine = _engine()
        low = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.1,
            leading_confidence=0.9,
        )
        high = engine.evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=3.0,
            leading_confidence=0.9,
        )
        assert high.confidence < low.confidence

    def test_uncertainty_exponent_convex(self):
        evaluator = BranchEvaluator(
            weights=EvaluatorWeights(
                outcome_weight=0.0,
                success_weight=0.0,
                risk_weight=0.0,
                cost_weight=0.0,
                uncertainty_weight=1.0,
                divergence_weight=0.0,
            ),
            uncertainty_exponent=2.0,
        )
        a = PlanBranch(
            label="A",
            label_ar="أ",
            steps=[_step()],
            expected_outcome=0.0,
            probability_of_success=0.0,
            risk_score=0.0,
            cost_score=0.0,
            uncertainty=0.9,
            divergence_cost=0.0,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        b = PlanBranch(
            label="B",
            label_ar="ب",
            steps=[_step()],
            expected_outcome=0.0,
            probability_of_success=0.0,
            risk_score=0.0,
            cost_score=0.0,
            uncertainty=0.45,
            divergence_cost=0.0,
            generated_from_trigger=RepairTrigger.BELIEF_SHIFT,
        )
        scores = evaluator.score([a, b])
        pen = {s.branch.label: s.uncertainty_penalty for s in scores}
        assert pen["A"] > 2.0 * pen["B"]


class TestRepairResult:
    def _result(self):
        plan = _plan(expected_dist={"a": 1.0, "b": 0.0})
        return _engine().evaluate(
            plan=plan,
            actual_dist={"a": 0.0, "b": 1.0},
            actual_entropy=0.0,
            leading_confidence=1.0,
        )

    def test_rationale_en_nonempty(self):
        result = self._result()
        assert result.rationale.strip()

    def test_rationale_ar_nonempty(self):
        result = self._result()
        assert result.rationale_ar.strip()

    def test_rationale_mentions_trigger(self):
        result = self._result()
        assert "trigger" in result.rationale.lower() or "المحفز" in result.rationale_ar

    def test_rationale_mentions_js_divergence(self):
        result = self._result()
        assert "js divergence" in result.rationale.lower()

    def test_rationale_mentions_confidence(self):
        result = self._result()
        assert "confidence" in result.rationale.lower()

    def test_all_branches_returns_selected_first(self):
        result = self._result()
        all_scores = result.all_branches()
        assert all_scores[0].branch.branch_id == result.selected_branch.branch.branch_id

    def test_frozen(self):
        result = self._result()
        with pytest.raises(ValidationError):
            result.rationale = "mutated"
