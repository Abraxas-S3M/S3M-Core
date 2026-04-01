"""Configuration for Copernicus Atmosphere Monitoring Service adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers.weather_openmeteo.config import SAUDI_LOCATIONS


DUST_AOD_THRESHOLDS: dict[str, float] = {
    "clear": 0.1,
    "light_haze": 0.3,
    "moderate_dust": 0.5,
    "heavy_dust": 1.0,
    "sandstorm": 2.0,
    "severe_storm": 999.0,
}


@dataclass(slots=True)
class CAMSConfig:
    ads_api_url: str = "https://ads.atmosphere.copernicus.eu/api/v2"
    forecast_api_url: str = "https://atmosphere.copernicus.eu/api/v1/forecast"
    rate_limit_rpm: int = 20
    saudi_bbox: dict[str, float] = field(default_factory=lambda: {"north": 32.0, "west": 34.0, "south": 16.0, "east": 56.0})
    dust_aod_thresholds: dict[str, float] = field(default_factory=lambda: dict(DUST_AOD_THRESHOLDS))
    variables_atmospheric: list[str] = field(default_factory=lambda: ["dust_aod", "pm10", "pm2_5", "total_aod", "uv_index"])
    variables_pollution: list[str] = field(default_factory=lambda: ["carbon_monoxide", "nitrogen_dioxide", "ozone", "sulphur_dioxide"])
    saudi_locations: dict[str, dict[str, float | str]] = field(default_factory=lambda: dict(SAUDI_LOCATIONS))
