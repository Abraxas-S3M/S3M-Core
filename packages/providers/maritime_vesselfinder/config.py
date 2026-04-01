"""Configuration for VesselFinder maritime provider integration."""

from __future__ import annotations

from dataclasses import dataclass, field


MONITORING_ZONES: dict[str, dict[str, float]] = {
    "persian_gulf": {"minlat": 24.0, "maxlat": 30.0, "minlon": 48.0, "maxlon": 56.0},
    "red_sea_south": {"minlat": 12.5, "maxlat": 15.0, "minlon": 42.0, "maxlon": 44.0},
    "strait_of_hormuz": {"minlat": 25.5, "maxlat": 26.5, "minlon": 56.0, "maxlon": 57.0},
    "bab_el_mandeb": {"minlat": 12.0, "maxlat": 13.5, "minlon": 43.0, "maxlon": 44.0},
    "jubail_coast": {"minlat": 26.8, "maxlat": 27.2, "minlon": 49.5, "maxlon": 49.8},
    "gulf_of_aden": {"minlat": 11.5, "maxlat": 14.0, "minlon": 44.0, "maxlon": 48.0},
}


@dataclass(slots=True)
class VesselFinderConfig:
    base_url: str = "https://api.vesselfinder.com"
    rate_limit_rpm: int = 5
    daily_quota: int = 100
    ais_type_map: list[tuple[int, int, str]] = field(
        default_factory=lambda: [
            (20, 29, "WIG"),
            (30, 39, "Fishing"),
            (40, 49, "HSC"),
            (50, 59, "Special"),
            (60, 69, "Passenger"),
            (70, 79, "Cargo"),
            (80, 89, "Tanker"),
            (90, 99, "Other"),
        ]
    )
    monitoring_zones: dict[str, dict[str, float]] = field(default_factory=lambda: dict(MONITORING_ZONES))
    saudi_ports: list[str] = field(
        default_factory=lambda: [
            "JUBAIL",
            "JEDDAH",
            "DAMMAM",
            "RAS TANURA",
            "YANBU",
            "KING ABDULLAH PORT",
        ]
    )
