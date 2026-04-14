"""
S3M Radar Adapter Framework

Bridges heterogeneous radar hardware into the S3M sensor fusion pipeline.
Models the Krechet 9C905 multi-radar integration capability: 10+ radar types
feeding a unified fused air picture through typed adapters with polar-to-
Cartesian conversion, RCS classification, and scan-to-scan plot correlation.

Data Flow:
  Physical Radar / Simulator -> RadarAdapter -> RadarManager -> SensorManager (Layer 02)
  -> TrackFuser -> ThreatEvents -> TargetAllocator (Air Defense)
"""

from services.radar.models import (
    RadarType,
    RadarBand,
    ScanMode,
    RadarPlot,
    RadarScan,
    RadarConfig,
    RadarStatus,
    RCSClassification,
)
from services.radar.coordinate_converter import CoordinateConverter
from services.radar.rcs_classifier import RCSClassifier
from services.radar.plot_correlator import PlotCorrelator
from services.radar.radar_manager import RadarManager

__all__ = [
    "RadarType",
    "RadarBand",
    "ScanMode",
    "RadarPlot",
    "RadarScan",
    "RadarConfig",
    "RadarStatus",
    "RCSClassification",
    "CoordinateConverter",
    "RCSClassifier",
    "PlotCorrelator",
    "RadarManager",
]
