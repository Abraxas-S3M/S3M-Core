"""Predictive defense service package.

Military context:
Exports deterministic prediction primitives used to support tactical defensive
posture decisions in disconnected command environments.
"""

from services.predictive_defense.models import (
    DefenseAlert,
    DefenseCommand,
    DefensePrediction,
    GenomeContext,
    SwarmAnalysis,
    ThreatPosture,
)
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager

__all__ = [
    "DefenseAlert",
    "DefenseCommand",
    "DefensePrediction",
    "GenomeContext",
    "PredictiveDefenseManager",
    "SwarmAnalysis",
    "ThreatPosture",
]

