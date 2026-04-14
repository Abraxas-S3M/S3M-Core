"""Radar sensing and multi-sensor track fusion services.

Military context:
Provides the tactical radar layer used to merge long-, medium-, and short-range
air-search detections into one coherent local air picture for C2 decisions.
"""

from services.radar.krechet_radar_suite import create_krechet_radar_suite
from services.radar.models import (
    FusedTrack,
    RCSClassification,
    RadarConfig,
    RadarPlot,
    RadarType,
    TrackState,
)
from services.radar.radar_manager import RadarManager

__all__ = [
    "FusedTrack",
    "RCSClassification",
    "RadarConfig",
    "RadarManager",
    "RadarPlot",
    "RadarType",
    "TrackState",
    "create_krechet_radar_suite",
]
