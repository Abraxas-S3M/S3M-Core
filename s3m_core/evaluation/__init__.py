"""S3M behavioral audit system exports."""

from .audit_runner import AuditReport, BehavioralAuditRunner, TranscriptWithScore
from .investigator import BehavioralInvestigator, InvestigationPlan, Transcript, TranscriptTurn
from .judge import BehavioralJudge
from .metrics import (
    ALL_METRICS,
    CHARACTER_METRICS,
    EVALUATION_OBSTACLE_METRICS,
    HONESTY_METRICS,
    SAFETY_METRICS,
    MetricResult,
)
from .scenario_library import SCENARIO_CATEGORIES, Scenario, ScenarioLibrary

__all__ = [
    "ALL_METRICS",
    "AuditReport",
    "BehavioralAuditRunner",
    "BehavioralInvestigator",
    "BehavioralJudge",
    "CHARACTER_METRICS",
    "EVALUATION_OBSTACLE_METRICS",
    "HONESTY_METRICS",
    "InvestigationPlan",
    "MetricResult",
    "SAFETY_METRICS",
    "SCENARIO_CATEGORIES",
    "Scenario",
    "ScenarioLibrary",
    "Transcript",
    "TranscriptTurn",
    "TranscriptWithScore",
]
"""Evaluation tooling for mission-safe model behavior analysis."""

from .eval_awareness import (
    EvalAwarenessDetector,
    EvalAwarenessScore,
    EvalAwarenessSuppressor,
    SandbagDetector,
    SandbagReport,
)

__all__ = [
    "EvalAwarenessScore",
    "EvalAwarenessDetector",
    "EvalAwarenessSuppressor",
    "SandbagReport",
    "SandbagDetector",
"""Evaluation utilities for measuring mission-assistant effectiveness."""

from .regression_tracker import Regression, RegressionTracker
from .uplift_scorer import Mission, RegressionReport, UpliftReport, UpliftScorer

__all__ = [
    "Mission",
    "Regression",
    "RegressionReport",
    "RegressionTracker",
    "UpliftReport",
    "UpliftScorer",
]
"""Evaluation primitives for constitution adherence scoring."""

from .constitution_scorer import (
    DIMENSIONS,
    AdherenceReport,
    AggregateReport,
    ComparisonReport,
    ConstitutionAdherenceScorer,
    ViolationDetail,
)

__all__ = [
    "DIMENSIONS",
    "AdherenceReport",
    "AggregateReport",
    "ComparisonReport",
    "ConstitutionAdherenceScorer",
    "ViolationDetail",
]

