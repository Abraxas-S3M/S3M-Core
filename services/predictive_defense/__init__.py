"""Predictive defense package for interceptor pre-positioning.

Military context:
Exports trajectory forecast models and tactical launch optimization used to
stage interceptors on likely hostile approach corridors before incursion.
"""

from services.predictive_defense.models import (
    InterceptWindow,
    PrePositionCommand,
    SwarmIntent,
    SwarmPrediction,
    ThreatTrajectoryPrediction,
)
from services.predictive_defense.preposition_optimizer import PrePositionOptimizer

__all__ = [
    "InterceptWindow",
    "PrePositionCommand",
    "PrePositionOptimizer",
    "SwarmIntent",
    "SwarmPrediction",
    "ThreatTrajectoryPrediction",
]
