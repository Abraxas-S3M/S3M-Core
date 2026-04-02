"""S3M Continuous Learning Feedback Interface.

Controlled, versioned feedback signals for prediction tuning.
No autonomous code rewriting — structured recommendations only.
"""
from .feedback_models import (
    FEEDBACK_SCHEMA_VERSION,
    FeedbackBatch,
    FeedbackSeverity,
    FeedbackSignal,
    FeedbackSignalType,
    FeedbackStatus,
    RecommendedAction,
)
from .feedback_signal_generator import FeedbackSignalGenerator

__all__ = [
    "FEEDBACK_SCHEMA_VERSION",
    "FeedbackBatch",
    "FeedbackSeverity",
    "FeedbackSignal",
    "FeedbackSignalType",
    "FeedbackStatus",
    "RecommendedAction",
    "FeedbackSignalGenerator",
]
