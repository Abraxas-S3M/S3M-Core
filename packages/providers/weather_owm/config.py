"""Configuration for OpenWeatherMap integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers.weather_openmeteo.config import SAUDI_LOCATIONS


@dataclass(slots=True)
class OWMConfig:
    base_url: str = "https://api.openweathermap.org"
    rate_limit_rpm: int = 60
    aqi_levels: dict[int, str] = field(default_factory=lambda: {
        1: "good",
        2: "fair",
        3: "moderate",
        4: "poor",
        5: "very_poor",
    })
    saudi_locations: dict[str, dict[str, float | str]] = field(default_factory=lambda: dict(SAUDI_LOCATIONS))
