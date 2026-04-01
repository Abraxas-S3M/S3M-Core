"""Configuration for Open-Meteo weather integration."""

from __future__ import annotations

from dataclasses import dataclass, field


OPERATIONAL_THRESHOLDS: dict[str, float] = {
    "visibility_flight_min_m": 1600,
    "visibility_ground_ops_min_m": 500,
    "wind_max_uav_kmh": 40,
    "wind_max_helicopter_kmh": 65,
    "temperature_max_operations_c": 52,
    "dust_sandstorm_threshold_ugm3": 200,
    "dust_severe_storm_ugm3": 500,
    "wave_max_usv_m": 2.5,
    "wave_max_patrol_boat_m": 4.0,
}


SAUDI_LOCATIONS: dict[str, dict[str, float | str]] = {
    "riyadh": {"lat": 24.71, "lon": 46.68, "name": "Riyadh (Central Command)"},
    "jeddah": {"lat": 21.54, "lon": 39.17, "name": "Jeddah (Western Region)"},
    "dhahran": {"lat": 26.43, "lon": 50.10, "name": "Dhahran (Eastern Province)"},
    "tabuk": {"lat": 28.38, "lon": 36.57, "name": "Tabuk (Northwest Border)"},
    "najran": {"lat": 17.49, "lon": 44.13, "name": "Najran (Yemen Border)"},
    "jubail": {"lat": 27.01, "lon": 49.66, "name": "Jubail (Industrial/Naval)"},
    "neom": {"lat": 27.95, "lon": 35.30, "name": "NEOM (Red Sea Coast)"},
    "sharurah": {"lat": 17.47, "lon": 47.12, "name": "Sharurah (Southern Border)"},
    "king_khalid_mil_city": {"lat": 18.30, "lon": 42.80, "name": "King Khalid Military City"},
    "strait_of_hormuz": {"lat": 26.0, "lon": 56.5, "name": "Strait of Hormuz (Maritime)"},
    "bab_el_mandeb": {"lat": 12.7, "lon": 43.3, "name": "Bab el-Mandeb (Maritime)"},
    "gulf_of_aden": {"lat": 12.5, "lon": 46.0, "name": "Gulf of Aden (Maritime)"},
}


@dataclass(slots=True)
class OpenMeteoConfig:
    forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    archive_url: str = "https://api.open-meteo.com/v1/archive"
    marine_url: str = "https://api.open-meteo.com/v1/marine"
    air_quality_url: str = "https://api.open-meteo.com/v1/air-quality"
    rate_limit_rpm: int = 60
    default_forecast_days: int = 7
    timezone: str = "Asia/Riyadh"
    operational_thresholds: dict[str, float] = field(default_factory=lambda: dict(OPERATIONAL_THRESHOLDS))
    hourly_params: list[str] = field(default_factory=lambda: [
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "visibility",
        "precipitation",
        "cloud_cover",
        "uv_index",
        "dust",
        "surface_pressure",
    ])
    marine_params: list[str] = field(default_factory=lambda: [
        "wave_height",
        "wave_period",
        "wave_direction",
        "swell_wave_height",
        "ocean_current_velocity",
    ])
    air_quality_params: list[str] = field(default_factory=lambda: [
        "pm10",
        "pm2_5",
        "dust",
        "aerosol_optical_depth",
        "uv_index",
    ])
    saudi_locations: dict[str, dict[str, float | str]] = field(default_factory=lambda: dict(SAUDI_LOCATIONS))
