"""Radar adapter services and data models.

Military context:
Exports radar-native detection and hardware abstractions used to ingest
Krechet-style plots into the shared S3M operational picture.
"""

from services.radar.models import (
    FusedTrack,
    PlotCorrelation,
    RCSClassification,
    RadarBand,
    RadarConfig,
    RadarPlot,
    RadarScan,
    RadarStatus,
    RadarUnit,
    RadarType,
    ScanMode,
    TrackState,
)
from services.radar.radar_manager import RadarManager
from services.radar.krechet_radar_suite import create_krechet_radar_suite

__all__ = [
    "FusedTrack",
    "PlotCorrelation",
    "RCSClassification",
    "RadarBand",
    "RadarConfig",
    "RadarPlot",
    "RadarManager",
    "RadarScan",
    "RadarStatus",
    "RadarUnit",
    "RadarType",
    "ScanMode",
    "TrackState",
    "create_krechet_radar_suite",
]
