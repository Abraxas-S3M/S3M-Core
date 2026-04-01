"""Configuration for Spire Maritime provider integration."""

from __future__ import annotations

from dataclasses import dataclass, field


ZONE_CENTERS: dict[str, dict[str, float]] = {
    "persian_gulf": {"lat": 27.0, "lon": 52.0, "radius_m": 400000.0},
    "red_sea_south": {"lat": 13.5, "lon": 43.0, "radius_m": 200000.0},
    "strait_of_hormuz": {"lat": 26.0, "lon": 56.5, "radius_m": 100000.0},
    "bab_el_mandeb": {"lat": 12.7, "lon": 43.3, "radius_m": 100000.0},
    "gulf_of_aden": {"lat": 12.5, "lon": 46.0, "radius_m": 300000.0},
    "red_sea_full": {"lat": 20.0, "lon": 38.0, "radius_m": 600000.0},
}


@dataclass(slots=True)
class SpireConfig:
    base_url: str = "https://api.spire.com/v2"
    rate_limit_rpm: int = 30
    default_radius_m: int = 200000
    zone_centers: dict[str, dict[str, float]] = field(default_factory=lambda: dict(ZONE_CENTERS))
