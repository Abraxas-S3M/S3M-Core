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

