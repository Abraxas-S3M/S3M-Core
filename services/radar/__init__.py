"""Radar surveillance service primitives for tactical air picture ingestion.

Military context:
Provides validated radar configuration and plot parsing components used to
ingest range/azimuth/elevation tracks into the common operating picture.
"""

from services.radar.models import RadarBand, RadarConfig, RadarPlot, RadarType, ScanMode

__all__ = [
    "RadarBand",
    "RadarConfig",
    "RadarPlot",
    "RadarType",
    "ScanMode",
]
