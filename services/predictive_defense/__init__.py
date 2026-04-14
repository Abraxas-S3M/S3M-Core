"""
S3M Predictive Threat Trajectory Engine

Beyond-Krechet capability: fuses radar tracks, threat genome behavioral
patterns, and short-horizon prediction to pre-position interceptor drones
and cue effectors 60-120 seconds BEFORE threats enter the defense zone.

Pipeline:
  RadarManager (fused tracks) → TrackGenomeBridge (genome correlation)
  → TrajectoryPredictor (genome-enhanced forecasts) → SwarmAnalyzer
  (convergence prediction) → PrePositionOptimizer (interceptor launch timing)
  → InterceptorManager + TargetAllocator (execute pre-emptive defense)
"""

from services.predictive_defense.models import (
    ThreatTrajectoryPrediction,
    SwarmPrediction,
    PrePositionCommand,
    InterceptWindow,
    PredictiveAlert,
    DefensePosture,
)

__all__ = [
    "ThreatTrajectoryPrediction",
    "SwarmPrediction",
    "PrePositionCommand",
    "InterceptWindow",
    "PredictiveAlert",
    "DefensePosture",
]
