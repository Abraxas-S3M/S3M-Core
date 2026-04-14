"""Radar data models for edge-deployed tactical sensing.

Military context:
These models define validated radar configuration and plot structures used
by tactical fusion layers to ingest detections from heterogeneous sensors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RadarType(str, Enum):
    AESA_WESTERN = "aesa_western"


class RadarBand(str, Enum):
    C_BAND = "c_band"


class ScanMode(str, Enum):
    ELECTRONIC = "electronic"


@dataclass
class RadarConfig:
    radar_id: str = "western-aesa"
    name_en: str = ""
    name_ar: str = ""
    radar_type: RadarType = RadarType.AESA_WESTERN
    band: RadarBand = RadarBand.C_BAND
    scan_mode: ScanMode = ScanMode.ELECTRONIC
    max_range_m: float = 0.0
    min_range_m: float = 0.0
    max_elevation_deg: float = 0.0
    has_elevation: bool = True
    has_doppler: bool = True
    beam_width_az_deg: float = 0.0
    beam_width_el_deg: float = 0.0
    scan_rate_rpm: float = 0.0
    update_rate_hz: float = 0.0
    min_detectable_rcs_dbsm: float = 0.0
    range_resolution_m: float = 0.0
    azimuth_resolution_deg: float = 0.0
    velocity_resolution_mps: float = 0.0
    range_noise_std_m: float = 0.0
    azimuth_noise_std_deg: float = 0.0
    elevation_noise_std_deg: float = 0.0


@dataclass
class RadarPlot:
    radar_id: str
    timestamp: datetime
    range_m: float
    azimuth_deg: float
    elevation_deg: float
    radial_velocity_mps: float
    rcs_dbsm: float
    snr_db: float
    signal_strength: float

