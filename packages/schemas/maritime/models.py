"""Normalized maritime schemas for vessel tracking and movement analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedVesselTrack(BaseNormalizedRecord):
    mmsi: str = ""
    imo: Optional[str] = None
    vessel_name: str = ""
    vessel_type: str = ""
    flag_state: str = ""
    speed_knots: float = 0.0
    course_deg: float = 0.0
    heading_deg: float = 0.0
    destination: Optional[str] = None
    eta: Optional[datetime] = None
    nav_status: str = ""
    draught_m: Optional[float] = None
    length_m: Optional[float] = None
    is_dark: bool = False


@dataclass
class PortCall:
    mmsi: str
    port_name: str
    arrival: datetime
    departure: Optional[datetime] = None


@dataclass
class VoyageHistory:
    mmsi: str
    route_points: List[str] = field(default_factory=list)
