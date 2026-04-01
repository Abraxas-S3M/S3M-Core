"""Normalized flight schemas for airspace monitoring and tactical air picture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedFlightTrack(BaseNormalizedRecord):
    icao24: str = ""
    callsign: str = ""
    aircraft_type: Optional[str] = None
    origin_airport: Optional[str] = None
    dest_airport: Optional[str] = None
    altitude_m: float = 0.0
    speed_knots: float = 0.0
    heading_deg: float = 0.0
    vertical_rate: float = 0.0
    squawk: Optional[str] = None
    on_ground: bool = False
    military: bool = False


@dataclass
class AircraftPosition:
    icao24: str
    lat: float
    lon: float
    altitude_m: float
