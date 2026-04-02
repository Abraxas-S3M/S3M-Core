"""Structured plan repair engine for tactical mission replanning."""

from __future__ import annotations

import copy
import logging
import math
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _normalize_distribution(dist: Dict[str, float]) -> Dict[str, float]:
    if not dist:
        return {}
    normalized: Dict[str, float] = {}
    total = 0.0
    for key, value in dist.items():
        if not isinstance(key, str) or not key.strip():
            continue
        numeric = float(value)
        if numeric < 0.0:
            numeric = 0.0
        normalized[key] = numeric
        total += numeric
    if total <= 0.0:
        return {}
    return {key: value / total for key, value in normalized.items()}


class PlanStatus(str, Enum):
    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"
    REPLANNED = "REPLANNED"


class StepType(str, Enum):
    MOVE = "MOVE"
    ENGAGE = "ENGAGE"
    HOLD = "HOLD"
    RECON = "RECON"
    SUPPORT = "SUPPORT"
    COORDINATE = "COORDINATE"
    EXFIL = "EXFIL"
    RTB = "RTB"
    WAIT = "WAIT"
    COMMUNICATE = "COMMUNICATE"
    UNKNOWN = "UNKNOWN"


class RepairTrigger(str, Enum):
    BELIEF_SHIFT = "BELIEF_SHIFT"
    HIGH_ENTROPY = "HIGH_ENTROPY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PLAN_EXPIRED = "PLAN_EXPIRED"
    COMBINED = "COMBINED"


class PlanStep(BaseModel):
    """Single tactical action within a mission plan."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(default_factory=_new_id)
    label: str
    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    step_type: StepType = StepType.UNKNOWN
    expected_duration_s: float = Field(default=60.0, ge=0.0)
    expected_success_prob: float = Field(default=0.8, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.2, ge=0.0, le=1.0)
    cost_score: float = Field(default=0.1, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be blank")
        return stripped


class MissionPlan(BaseModel):
    """Mission plan snapshot used as the baseline for tactical repair."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=_new_id)
    label: str
    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    steps: List[PlanStep] = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)
    expected_belief_distribution: Dict[str, float] = Field(default_factory=dict)
    expected_completion_prob: float = Field(default=0.8, ge=0.0, le=1.0)
    expected_outcome: float = Field(default=0.8, ge=0.0, le=1.0)
    overall_risk: float = Field(default=0.2, ge=0.0, le=1.0)
    version: int = Field(default=1, ge=0)
    parent_plan_id: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be blank")
        return stripped

    @field_validator("expected_belief_distribution")
    @classmethod
    def _validate_expected_distribution(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not value:
            return {}
        total = 0.0
        validated: Dict[str, float] = {}
        for key, prob in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("expected_belief_distribution keys must be non-empty strings")
            numeric = float(prob)
            if numeric < 0.0:
                raise ValueError("expected_belief_distribution probabilities must be non-negative")
            validated[key] = numeric
            total += numeric
        if abs(total - 1.0) > 0.01:
            raise ValueError("expected_belief_distribution must sum to 1.0 (+/- 0.01)")
        return validated

    def total_expected_duration_s(self) -> float:
        """Return total expected mission duration in seconds."""
        return float(sum(step.expected_duration_s for step in self.steps))

    def average_step_risk(self) -> float:
        """Return mean tactical risk across all mission steps."""
        if not self.steps:
            return 0.0
        return float(sum(step.risk_score for step in self.steps) / len(self.steps))

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        """Return plan age in seconds relative to current UTC time."""
        current_time = now or _utc_now()
        return max(0.0, float((current_time - self.created_at).total_seconds()))


class BeliefShiftReport(BaseModel):
    """Numerical divergence report between expected and observed beliefs."""

    model_config = ConfigDict(frozen=True)

    report_id: str = Field(default_factory=_new_id)
    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    js_divergence: float = Field(ge=0.0)
    kl_divergence_fwd: float = Field(ge=0.0)
    entropy_actual: float = Field(ge=0.0)
    entropy_expected: float = Field(ge=0.0)
    entropy_delta: float
    leading_confidence: float = Field(ge=0.0, le=1.0)
    shift_magnitude: float = Field(ge=0.0, le=1.0)
    triggers: List[RepairTrigger]
    plan_status: PlanStatus
    timestamp: datetime = Field(default_factory=_utc_now)

    def repair_required(self) -> bool:
        """Return whether numerical divergence indicates plan repair is required."""
        return self.plan_status in {PlanStatus.FAILED, PlanStatus.UNCERTAIN} or bool(self.triggers)


class PlanBranch(BaseModel):
    """Candidate repaired branch derived from a baseline tactical plan."""

    model_config = ConfigDict(frozen=True)

    branch_id: str = Field(default_factory=_new_id)
    label: str
    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    steps: List[PlanStep] = Field(min_length=1)
    expected_outcome: float = Field(ge=0.0, le=1.0)
    probability_of_success: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    cost_score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    divergence_cost: float = Field(default=0.0, ge=0.0, le=1.0)
    generated_from_trigger: RepairTrigger
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def raw_ev(self) -> float:
        """Return raw expected value as success probability times outcome."""
        return float(self.probability_of_success * self.expected_outcome)


class BranchScore(BaseModel):
    """Scored branch with utility decomposition and ranking."""

    model_config = ConfigDict(frozen=True)

    branch: PlanBranch
    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    utility: float
    ev_component: float
    risk_penalty: float
    cost_penalty: float
    uncertainty_penalty: float
    divergence_penalty: float
    rank: int = 0


class EvaluatorWeights(BaseModel):
    """Normalized multi-objective weights for branch evaluation."""

    model_config = ConfigDict(frozen=True)

    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    outcome_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    success_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    risk_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    cost_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    uncertainty_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    divergence_weight: float = Field(default=0.05, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_sum(self) -> "EvaluatorWeights":
        total = (
            self.outcome_weight
            + self.success_weight
            + self.risk_weight
            + self.cost_weight
            + self.uncertainty_weight
            + self.divergence_weight
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("EvaluatorWeights must sum to 1.0 (+/- 0.001)")
        return self

    @classmethod
    def conservative(cls) -> "EvaluatorWeights":
        """Return risk-averse tactical weighting for safer branch selection."""
        return cls(
            outcome_weight=0.20,
            success_weight=0.20,
            risk_weight=0.30,
            cost_weight=0.10,
            uncertainty_weight=0.15,
            divergence_weight=0.05,
        )

    @classmethod
    def aggressive(cls) -> "EvaluatorWeights":
        """Return outcome-focused tactical weighting for decisive maneuvers."""
        return cls(
            outcome_weight=0.40,
            success_weight=0.30,
            risk_weight=0.10,
            cost_weight=0.05,
            uncertainty_weight=0.10,
            divergence_weight=0.05,
        )


class BranchGeneratorConfig(BaseModel):
    """Deterministic configuration for tactical repair branch generation."""

    model_config = ConfigDict(frozen=True)

    label_ar: Optional[str] = None
    rationale_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    n_branches: int = Field(default=5, ge=1, le=20)
    uncertainty_exponent: float = Field(default=2.0, gt=0.0)
    max_divergence_penalty: float = Field(default=0.3, ge=0.0, le=1.0)
    preserve_step_types: bool = True
    seed_factor: float = Field(default=0.05, gt=0.0)


class RepairResult(BaseModel):
    """Final result of a numerical tactical replanning cycle."""

    model_config = ConfigDict(frozen=True)

    result_id: str = Field(default_factory=_new_id)
    label_ar: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    notes_ar: Optional[str] = None
    original_plan: MissionPlan
    shift_report: BeliefShiftReport
    selected_branch: BranchScore
    alternative_branches: List[BranchScore]
    repaired_plan: MissionPlan
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    rationale_ar: str
    computation_ms: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=_utc_now)

    def all_branches(self) -> List[BranchScore]:
        """Return selected branch followed by ranked alternatives."""
        return [self.selected_branch, *self.alternative_branches]

    def improvement(self) -> float:
        """Return utility gain against naive original-plan expected value."""
        naive_ref = self.original_plan.expected_completion_prob * self.original_plan.expected_outcome
        return float(self.selected_branch.utility - naive_ref)


class BeliefShiftDetector:
    """Compute numerical belief divergence to determine tactical plan status."""

    def __init__(
        self,
        shift_threshold: float = 0.25,
        failure_threshold: float = 0.50,
        entropy_threshold: float = 2.0,
        confidence_threshold: float = 0.35,
        max_plan_age_seconds: float = 300.0,
    ) -> None:
        self.shift_threshold = float(shift_threshold)
        self.failure_threshold = float(failure_threshold)
        self.entropy_threshold = float(entropy_threshold)
        self.confidence_threshold = float(confidence_threshold)
        self.max_plan_age_seconds = float(max_plan_age_seconds)

    def detect(
        self,
        plan: MissionPlan,
        actual_dist: Dict[str, float],
        actual_entropy: float,
        leading_confidence: float,
        plan_age_seconds: Optional[float] = None,
    ) -> BeliefShiftReport:
        """Detect numerical tactical belief shift and return a structured report."""
        actual = _normalize_distribution(actual_dist or {})
        expected = _normalize_distribution(plan.expected_belief_distribution)

        if not expected:
            js_div = 0.0
            kl_fwd = 0.0
        else:
            aligned_actual, aligned_expected = self._align(actual, expected, eps=1e-10)
            midpoint = {key: 0.5 * (aligned_actual[key] + aligned_expected[key]) for key in aligned_actual}
            js_div = 0.5 * self._kl(aligned_actual, midpoint) + 0.5 * self._kl(aligned_expected, midpoint)
            js_div = _clamp(js_div, 0.0, 1.0)
            kl_fwd = self._kl(aligned_actual, aligned_expected)

        entropy_expected = self._entropy(expected) if expected else 0.0
        entropy_delta = float(actual_entropy - entropy_expected)
        entropy_denominator = max(1.0, max(entropy_expected, 0.01))
        entropy_delta_norm = _clamp(entropy_delta / entropy_denominator, 0.0, 1.0)
        shift_magnitude = _clamp(0.5 * js_div + 0.5 * entropy_delta_norm, 0.0, 1.0)

        triggers: List[RepairTrigger] = []
        if js_div > self.failure_threshold:
            triggers.append(RepairTrigger.BELIEF_SHIFT)
        elif js_div > self.shift_threshold:
            triggers.append(RepairTrigger.BELIEF_SHIFT)
        if actual_entropy > self.entropy_threshold:
            triggers.append(RepairTrigger.HIGH_ENTROPY)
        if leading_confidence < self.confidence_threshold:
            triggers.append(RepairTrigger.LOW_CONFIDENCE)
        if plan_age_seconds is not None and plan_age_seconds > self.max_plan_age_seconds:
            triggers.append(RepairTrigger.PLAN_EXPIRED)
        if len(triggers) > 1 and RepairTrigger.BELIEF_SHIFT in triggers:
            triggers = [RepairTrigger.COMBINED]

        if not triggers:
            status = PlanStatus.NOMINAL
        elif js_div > self.failure_threshold or RepairTrigger.COMBINED in triggers:
            status = PlanStatus.FAILED
        elif RepairTrigger.HIGH_ENTROPY in triggers and leading_confidence < self.confidence_threshold:
            status = PlanStatus.UNCERTAIN
        else:
            status = PlanStatus.DEGRADED

        return BeliefShiftReport(
            js_divergence=js_div,
            kl_divergence_fwd=max(0.0, float(kl_fwd)),
            entropy_actual=max(0.0, float(actual_entropy)),
            entropy_expected=max(0.0, float(entropy_expected)),
            entropy_delta=entropy_delta,
            leading_confidence=_clamp(float(leading_confidence), 0.0, 1.0),
            shift_magnitude=shift_magnitude,
            triggers=triggers,
            plan_status=status,
        )

    def _kl(self, p_dict: Dict[str, float], q_dict: Dict[str, float], eps: float = 1e-10) -> float:
        total = 0.0
        for key, p_value in p_dict.items():
            p = max(float(p_value), eps)
            q = max(float(q_dict.get(key, eps)), eps)
            total += p * math.log(p / q)
        return max(0.0, float(total))

    def _entropy(self, dist: Dict[str, float]) -> float:
        normalized = _normalize_distribution(dist)
        entropy = 0.0
        for prob in normalized.values():
            p = float(prob)
            if p > 0.0:
                entropy -= p * math.log(p)
        return max(0.0, float(entropy))

    def _align(self, p: Dict[str, float], q: Dict[str, float], eps: float) -> Tuple[Dict[str, float], Dict[str, float]]:
        keys = set(p.keys()) | set(q.keys())
        aligned_p = {key: max(float(p.get(key, 0.0)), eps) for key in keys}
        aligned_q = {key: max(float(q.get(key, 0.0)), eps) for key in keys}
        return _normalize_distribution(aligned_p), _normalize_distribution(aligned_q)


class BranchGenerator:
    """Generate deterministic tactical repair branches from a baseline plan."""

    def __init__(self, config: Optional[BranchGeneratorConfig] = None) -> None:
        self.config = config or BranchGeneratorConfig()

    def generate(
        self,
        plan: MissionPlan,
        shift_report: BeliefShiftReport,
        actual_dist: Dict[str, float],
    ) -> List[PlanBranch]:
        """Generate deterministic mission branches using numerical perturbation."""
        normalized_actual = _normalize_distribution(actual_dist or {})
        generated: List[PlanBranch] = []
        base_cost = float(sum(step.cost_score for step in plan.steps) / len(plan.steps))
        max_hypothesis_entropy = max(1.0, math.log(max(2, len(normalized_actual))))

        for i in range(self.config.n_branches):
            factor = _clamp(1.0 - (i * self.config.seed_factor), 0.5, 1.0)

            branch_steps = list(plan.steps)
            if self.config.preserve_step_types:
                rebuilt_steps: List[PlanStep] = []
                for step in plan.steps:
                    adjusted_prob = _clamp(step.expected_success_prob * factor, 0.05, 0.99)
                    rebuilt_steps.append(step.model_copy(update={"expected_success_prob": adjusted_prob}))
                branch_steps = rebuilt_steps

            probability_product = 1.0
            for step in branch_steps:
                probability_product *= _clamp(step.expected_success_prob, 0.0, 1.0)
            probability_of_success = probability_product ** (1.0 / max(1, len(branch_steps)))

            expected_outcome = _clamp(plan.expected_outcome * factor, 0.0, 1.0)
            risk_score = _clamp(plan.overall_risk * (2.0 - factor), 0.0, 1.0)
            cost_score = _clamp(base_cost * (1.0 + (1.0 - factor)), 0.0, 1.0)
            uncertainty = _clamp(shift_report.entropy_actual / max_hypothesis_entropy, 0.0, 1.0)
            divergence_cost = _clamp(1.0 - factor, 0.0, 1.0)
            trigger = shift_report.triggers[0] if shift_report.triggers else RepairTrigger.BELIEF_SHIFT

            generated.append(
                PlanBranch(
                    label=f"Branch-{i + 1}: {plan.label} (repair factor={factor:.2f})",
                    label_ar=f"الفرع-{i + 1}: إصلاح بعامل {factor:.2f}",
                    steps=branch_steps,
                    expected_outcome=expected_outcome,
                    probability_of_success=probability_of_success,
                    risk_score=risk_score,
                    cost_score=cost_score,
                    uncertainty=uncertainty,
                    divergence_cost=divergence_cost,
                    generated_from_trigger=trigger,
                    metadata={"source_plan_id": plan.plan_id, "repair_factor": factor},
                )
            )
        return generated


class BranchEvaluator:
    """Score mission branches with weighted tactical utility."""

    def __init__(
        self,
        weights: Optional[EvaluatorWeights] = None,
        uncertainty_exponent: float = 2.0,
        max_divergence_penalty: float = 0.3,
    ) -> None:
        self.weights = weights or EvaluatorWeights()
        self.uncertainty_exponent = float(uncertainty_exponent)
        self.max_divergence_penalty = _clamp(max_divergence_penalty, 0.0, 1.0)

    def score(self, branches: List[PlanBranch]) -> List[BranchScore]:
        """Score and rank branch candidates from best utility to worst."""
        if not branches:
            return []

        scored: List[BranchScore] = []
        for branch in branches:
            ev_component = (
                self.weights.outcome_weight * branch.expected_outcome
                + self.weights.success_weight * branch.probability_of_success
            )
            risk_penalty = self.weights.risk_weight * branch.risk_score
            cost_penalty = self.weights.cost_weight * branch.cost_score
            uncertainty_penalty = self.weights.uncertainty_weight * (
                branch.uncertainty ** self.uncertainty_exponent
            )
            divergence_penalty = self.weights.divergence_weight * min(
                branch.divergence_cost, self.max_divergence_penalty
            )
            utility = _clamp(
                ev_component - risk_penalty - cost_penalty - uncertainty_penalty - divergence_penalty,
                -1.0,
                1.0,
            )
            scored.append(
                BranchScore(
                    branch=branch,
                    utility=utility,
                    ev_component=ev_component,
                    risk_penalty=risk_penalty,
                    cost_penalty=cost_penalty,
                    uncertainty_penalty=uncertainty_penalty,
                    divergence_penalty=divergence_penalty,
                )
            )

        sorted_scores = sorted(scored, key=lambda item: item.utility, reverse=True)
        return [score.model_copy(update={"rank": index}) for index, score in enumerate(sorted_scores, start=1)]


class PlanRepairEngine:
    """End-to-end tactical replanning engine based on numerical belief divergence."""

    def __init__(
        self,
        shift_detector: Optional[BeliefShiftDetector] = None,
        branch_generator: Optional[BranchGenerator] = None,
        branch_evaluator: Optional[BranchEvaluator] = None,
        min_improvement_to_repair: float = 0.0,
    ) -> None:
        self.shift_detector = shift_detector or BeliefShiftDetector()
        self.branch_generator = branch_generator or BranchGenerator()
        self.branch_evaluator = branch_evaluator or BranchEvaluator(
            max_divergence_penalty=self.branch_generator.config.max_divergence_penalty,
            uncertainty_exponent=self.branch_generator.config.uncertainty_exponent,
        )
        self.min_improvement_to_repair = float(min_improvement_to_repair)

    def evaluate(
        self,
        plan: MissionPlan,
        belief_state: Any = None,
        actual_dist: Optional[Dict[str, float]] = None,
        actual_entropy: Optional[float] = None,
        leading_confidence: Optional[float] = None,
        plan_age_seconds: Optional[float] = None,
        author_id: Optional[str] = None,
    ) -> RepairResult:
        """Evaluate belief divergence and produce a deterministic repaired mission plan."""
        start = time.perf_counter()
        snapshot_id: Optional[str] = None

        if belief_state is not None:
            try:
                from src.belief_state.models import BeliefState  # type: ignore
            except ImportError:
                BeliefState = None  # type: ignore
            if BeliefState is not None and isinstance(belief_state, BeliefState):
                actual_dist = copy.deepcopy(getattr(belief_state, "confidence_distribution", {}) or {})
                actual_entropy = float(belief_state.entropy())
                leading_confidence = max(actual_dist.values(), default=0.5)
                snapshot_id = getattr(belief_state, "state_id", None)

        active_dist = _normalize_distribution(actual_dist or {})
        active_entropy = float(actual_entropy if actual_entropy is not None else 0.0)
        lead_conf = float(
            leading_confidence
            if leading_confidence is not None
            else (max(active_dist.values(), default=1.0) if active_dist else 1.0)
        )
        age_seconds = plan_age_seconds if plan_age_seconds is not None else plan.age_seconds()

        shift_report = self.shift_detector.detect(
            plan=plan,
            actual_dist=active_dist,
            actual_entropy=active_entropy,
            leading_confidence=lead_conf,
            plan_age_seconds=age_seconds,
        )

        if not shift_report.repair_required():
            selected_branch = self._trivial_branch(plan, shift_report)
            return RepairResult(
                original_plan=plan,
                shift_report=shift_report,
                selected_branch=selected_branch,
                alternative_branches=[],
                repaired_plan=plan,
                confidence=_clamp(lead_conf, 0.0, 1.0),
                rationale="No repair required. Plan is NOMINAL.",
                rationale_ar="لا يلزم إصلاح. الخطة مستقرة.",
                computation_ms=max((time.perf_counter() - start) * 1000.0, 0.001),
                notes_ar=(f"snapshot_id={snapshot_id}" if snapshot_id else None),
            )

        branches = self.branch_generator.generate(plan=plan, shift_report=shift_report, actual_dist=active_dist)
        scored_branches = self.branch_evaluator.score(branches)
        best_branch = scored_branches[0] if scored_branches else self._trivial_branch(plan, shift_report)

        naive_ev = plan.expected_completion_prob * plan.expected_outcome
        selected_branch = best_branch
        alternative_branches = scored_branches[1:]
        threshold_blocked = best_branch.utility < (naive_ev + self.min_improvement_to_repair)
        if threshold_blocked:
            selected_branch = self._trivial_branch(plan, shift_report)
            alternative_branches = [
                score.model_copy(update={"rank": idx})
                for idx, score in enumerate(scored_branches, start=2)
            ]

        expected_distribution = active_dist or plan.expected_belief_distribution
        expected_distribution = _normalize_distribution(expected_distribution)
        repaired_plan = MissionPlan(
            label=f"[REPAIR v{plan.version + 1}] {plan.label}",
            label_ar=f"[إصلاح v{plan.version + 1}] {plan.label_ar or plan.label}",
            steps=selected_branch.branch.steps,
            expected_belief_distribution=expected_distribution,
            expected_completion_prob=selected_branch.branch.probability_of_success,
            expected_outcome=selected_branch.branch.expected_outcome,
            overall_risk=selected_branch.branch.risk_score,
            version=plan.version + 1,
            parent_plan_id=plan.plan_id,
            notes_ar=(f"author_id={author_id}" if author_id else None),
        )

        confidence = lead_conf * selected_branch.branch.probability_of_success
        confidence *= math.exp(-0.1 * shift_report.entropy_actual)
        confidence = _clamp(confidence, 0.0, 1.0)
        improvement_value = selected_branch.utility - naive_ev
        branch_count = len(scored_branches)

        rationale = self._rationale_en(
            shift_report=shift_report,
            selected_branch=selected_branch,
            naive_ev=naive_ev,
            branch_count=branch_count,
            confidence=confidence,
            improvement_value=improvement_value,
            threshold_blocked=threshold_blocked,
        )
        rationale_ar = self._rationale_ar(
            shift_report=shift_report,
            selected_branch=selected_branch,
            naive_ev=naive_ev,
            branch_count=branch_count,
            confidence=confidence,
            improvement_value=improvement_value,
            threshold_blocked=threshold_blocked,
        )

        return RepairResult(
            original_plan=plan,
            shift_report=shift_report,
            selected_branch=selected_branch,
            alternative_branches=alternative_branches,
            repaired_plan=repaired_plan,
            confidence=confidence,
            rationale=rationale,
            rationale_ar=rationale_ar,
            computation_ms=max((time.perf_counter() - start) * 1000.0, 0.001),
            notes_ar=(f"snapshot_id={snapshot_id}" if snapshot_id else None),
        )

    def _trivial_branch(self, plan: MissionPlan, shift_report: BeliefShiftReport) -> BranchScore:
        base_cost = float(sum(step.cost_score for step in plan.steps) / len(plan.steps))
        branch = PlanBranch(
            label=f"Nominal: {plan.label}",
            label_ar=f"اسمي: {plan.label_ar or plan.label}",
            steps=plan.steps,
            expected_outcome=plan.expected_outcome,
            probability_of_success=plan.expected_completion_prob,
            risk_score=plan.overall_risk,
            cost_score=base_cost,
            uncertainty=_clamp(shift_report.entropy_actual / max(1.0, math.log(2.0)), 0.0, 1.0),
            divergence_cost=0.0,
            generated_from_trigger=shift_report.triggers[0]
            if shift_report.triggers
            else RepairTrigger.BELIEF_SHIFT,
            metadata={"source_plan_id": plan.plan_id, "mode": "trivial"},
        )
        naive_ev = plan.expected_completion_prob * plan.expected_outcome
        return BranchScore(
            branch=branch,
            utility=naive_ev,
            ev_component=naive_ev,
            risk_penalty=0.0,
            cost_penalty=0.0,
            uncertainty_penalty=0.0,
            divergence_penalty=0.0,
            rank=1,
        )

    def _rationale_en(
        self,
        shift_report: BeliefShiftReport,
        selected_branch: BranchScore,
        naive_ev: float,
        branch_count: int,
        confidence: float,
        improvement_value: float,
        threshold_blocked: bool,
    ) -> str:
        triggers = ", ".join(trigger.value for trigger in shift_report.triggers) if shift_report.triggers else "NONE"
        note = (
            " Improvement threshold prevented branch adoption; baseline steps were retained."
            if threshold_blocked
            else ""
        )
        return (
            f"Repair triggers: {triggers}. JS divergence={shift_report.js_divergence:.4f}. "
            f"Selected branch='{selected_branch.branch.label}' rank={selected_branch.rank}. "
            f"Utility={selected_branch.utility:.4f} vs naive_ev={naive_ev:.4f}. "
            f"Branches evaluated={branch_count}. Confidence={confidence:.4f}. "
            f"Improvement={improvement_value:.4f}.{note}"
        )

    def _rationale_ar(
        self,
        shift_report: BeliefShiftReport,
        selected_branch: BranchScore,
        naive_ev: float,
        branch_count: int,
        confidence: float,
        improvement_value: float,
        threshold_blocked: bool,
    ) -> str:
        triggers = "، ".join(trigger.value for trigger in shift_report.triggers) if shift_report.triggers else "NONE"
        note = " تم رفض اعتماد الفرع بسبب حد التحسن وتم الإبقاء على خطوات الخطة الأصلية." if threshold_blocked else ""
        return (
            f"محفزات الإصلاح: {triggers}. قيمة تباعد JS={shift_report.js_divergence:.4f}. "
            f"الفرع المختار='{selected_branch.branch.label}' بالترتيب={selected_branch.rank}. "
            f"المنفعة={selected_branch.utility:.4f} مقابل المرجع={naive_ev:.4f}. "
            f"عدد الفروع المقيمة={branch_count}. الثقة={confidence:.4f}. "
            f"التحسن={improvement_value:.4f}.{note}"
        )

