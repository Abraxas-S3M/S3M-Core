"""S3M Online Learning — incremental adaptation without full retraining."""

from .stream_learner import (
    OnlineSGDClassifier,
    OnlineTreeEnsemble,
    PredictionRecord,
    StreamConfig,
    StreamLearner,
)

__all__ = [
    "StreamLearner",
    "OnlineSGDClassifier",
    "OnlineTreeEnsemble",
    "StreamConfig",
    "PredictionRecord",
]
