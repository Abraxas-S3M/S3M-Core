"""Normalized weather schemas for operational planning in harsh environments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedWeatherObservation(BaseNormalizedRecord):
    temperature_c: float = 0.0
    humidity_pct: float = 0.0
    wind_speed_mps: float = 0.0
    wind_direction_deg: float = 0.0
    visibility_km: float = 0.0
    precipitation_mm: float = 0.0
    pressure_hpa: float = 0.0
    cloud_cover_pct: float = 0.0
    uv_index: Optional[float] = None
    dust_concentration: Optional[float] = None
    forecast_hours: Optional[int] = None


@dataclass
class Forecast:
    issued_at: datetime
    forecast_hours: int


@dataclass
class DustAlert:
    level: str
    concentration: float
