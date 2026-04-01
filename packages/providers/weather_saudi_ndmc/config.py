"""Configuration for Saudi NDMC hybrid weather ingestion adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers.weather_openmeteo.config import SAUDI_LOCATIONS

SAUDI_AIRPORTS: dict[str, str] = {
    "OERK": "King Khalid International (Riyadh)",
    "OEJN": "King Abdulaziz International (Jeddah)",
    "OEDF": "King Fahd International (Dammam)",
    "OETB": "Tabuk Regional",
    "OEAB": "Abha Regional",
    "OEMA": "Prince Mohammed bin Abdulaziz (Madinah)",
    "OEGN": "Gizan Regional (Jizan)",
    "OEGS": "Sharourah Airport",
    "OEJB": "Jubail Airport",
    "OENR": "Najran Airport",
    "OEKK": "King Khalid Military City",
    "OEYN": "Yanbu Airport",
}

METAR_DUST_CODES: list[str] = ["HZ", "DU", "SA", "DS", "SS", "BLDU", "BLSA"]


@dataclass(slots=True)
class SaudiNDMCConfig:
    incoming_dir: str = "data/integrations/weather-saudi-ndmc/incoming/"
    rate_limit_rpm: int = 10
    saudi_airports: dict[str, str] = field(default_factory=lambda: dict(SAUDI_AIRPORTS))
    metar_dust_codes: list[str] = field(default_factory=lambda: list(METAR_DUST_CODES))
    ndmc_alert_types: list[str] = field(default_factory=lambda: [
        "dust_storm",
        "sand_storm",
        "extreme_heat",
        "thunderstorm",
        "flash_flood",
        "strong_wind",
        "cold_wave",
        "fog",
    ])
    extreme_heat_threshold_c: int = 50
    saudi_locations: dict[str, dict[str, float | str]] = field(default_factory=lambda: dict(SAUDI_LOCATIONS))
