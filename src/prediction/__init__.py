"""Short-horizon tactical prediction package for S3M.

This package is designed for offline, air-gapped operation on edge hardware.
"""

from .prediction_models import (
    EntitySnapshot,
    ExplanationBlock,
    ForecastBundle,
    ForecastWindow,
    PredictedEntityState,
    PredictionHypothesis,
    ThreatPosture,
    UncertaintyEstimate,
)
from .short_horizon_predictor import ShortHorizonPredictor

__all__ = [
    "EntitySnapshot",
    "ExplanationBlock",
    "ForecastBundle",
    "ForecastWindow",
    "PredictedEntityState",
    "PredictionHypothesis",
    "ShortHorizonPredictor",
    "ThreatPosture",
    "UncertaintyEstimate",
]
