"""S3M evaluation tooling for behavioral audits and release metrics."""

from .audit_runner import AuditReport, BehavioralAuditRunner, TranscriptWithScore
from .constitution_scorer import (
    DIMENSIONS,
    AdherenceReport,
    AggregateReport,
    ComparisonReport,
    ConstitutionAdherenceScorer,
    ViolationDetail,
)
from .eval_awareness import (
    EvalAwarenessDetector,
    EvalAwarenessScore,
    EvalAwarenessSuppressor,
    SandbagDetector,
    SandbagReport,
)
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
from .regression_tracker import Regression, RegressionTracker
from .scenario_library import SCENARIO_CATEGORIES, Scenario, ScenarioLibrary
from .uplift_scorer import Mission, RegressionReport, UpliftReport, UpliftScorer

__all__ = [
    "ALL_METRICS",
    "AdherenceReport",
    "AggregateReport",
    "AuditReport",
    "BehavioralAuditRunner",
    "BehavioralInvestigator",
    "BehavioralJudge",
    "CHARACTER_METRICS",
    "ComparisonReport",
    "ConstitutionAdherenceScorer",
    "DIMENSIONS",
    "EVALUATION_OBSTACLE_METRICS",
    "EvalAwarenessDetector",
    "EvalAwarenessScore",
    "EvalAwarenessSuppressor",
    "HONESTY_METRICS",
    "InvestigationPlan",
    "MetricResult",
    "Mission",
    "Regression",
    "RegressionReport",
    "RegressionTracker",
    "SAFETY_METRICS",
    "SCENARIO_CATEGORIES",
    "SandbagDetector",
    "SandbagReport",
    "Scenario",
    "ScenarioLibrary",
    "Transcript",
    "TranscriptTurn",
    "TranscriptWithScore",
    "UpliftReport",
    "UpliftScorer",
    "ViolationDetail",
]
