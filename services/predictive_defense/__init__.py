"""Predictive defense services.

Military context:
Exposes genome-aware forecasting components used by tactical C2 loops to
anticipate adversary approach doctrine before engagement commitment.
"""

from services.predictive_defense.models import ThreatTrajectoryPrediction
from services.predictive_defense.trajectory_predictor import TrajectoryPredictor

__all__ = [
    "ThreatTrajectoryPrediction",
    "TrajectoryPredictor",
]
