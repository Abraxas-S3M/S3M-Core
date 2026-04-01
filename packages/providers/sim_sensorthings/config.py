"""Configuration for simulation-only OGC SensorThings interoperability."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


S3M_SENSOR_TYPES: dict[str, dict[str, list[str]]] = {
    "ground_radar": {
        "properties": ["target_range_km", "target_bearing_deg", "rcs_dbsm", "target_velocity_mps"]
    },
    "weather_station": {
        "properties": ["temperature_c", "wind_speed_mps", "visibility_m", "dust_ugm3"]
    },
    "seismic_sensor": {"properties": ["magnitude", "frequency_hz", "ground_velocity_mms"]},
    "chemical_detector": {"properties": ["agent_type", "concentration_ppm", "alarm_level"]},
    "radiation_monitor": {"properties": ["dose_rate_usv_h", "cumulative_dose_usv", "alarm_level"]},
    "acoustic_sensor": {"properties": ["sound_level_db", "frequency_hz", "bearing_deg", "classification"]},
    "ais_receiver": {"properties": ["mmsi", "lat", "lon", "speed_knots", "heading_deg"]},
}


@dataclass(slots=True)
class SensorThingsConfig:
    base_url: str = field(default_factory=lambda: os.getenv("S3M_SENSORTHINGS_URL", "http://localhost:8080/FROST-Server/v1.1"))
    rate_limit_rpm: int = 60
    s3m_sensor_types: dict[str, Any] = field(default_factory=lambda: dict(S3M_SENSOR_TYPES))
    odata_max_top: int = 1000
