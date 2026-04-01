"""Normalized geospatial schemas for satellite and imagery providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ..common.base import BaseNormalizedRecord, GeoPoint


@dataclass
class NormalizedGeoObservation(BaseNormalizedRecord):
    observation_type: str = "optical"
    satellite: str = ""
    resolution_m: float = 0.0
    cloud_cover_pct: Optional[float] = None
    footprint: List[GeoPoint] = field(default_factory=list)
    imagery_url: Optional[str] = None
    bands: List[str] = field(default_factory=list)
    acquisition_time: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SatellitePass:
    satellite: str
    pass_start: datetime
    pass_end: datetime
    orbit_number: Optional[int] = None


@dataclass
class ImageryFootprint:
    observation_id: str
    corners: List[GeoPoint] = field(default_factory=list)
