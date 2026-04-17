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

