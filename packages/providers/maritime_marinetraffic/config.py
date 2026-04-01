"""Configuration for MarineTraffic maritime provider integration."""

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
class MarineTrafficConfig:
    base_url: str = "https://services.marinetraffic.com/api"
    rate_limit_rpm: int = 10
    default_timespan_minutes: int = 60
    speed_divisor: float = 10.0
    draught_divisor: float = 10.0
    ship_type_names: dict[int, str] = field(
        default_factory=lambda: {
            1: "Reserved",
            2: "WIG",
            3: "Vessel",
            4: "HSC",
            5: "Special",
            6: "Passenger",
            7: "Cargo",
            8: "Tanker",
            9: "Other",
        }
    )
    nav_status_names: dict[int, str] = field(
        default_factory=lambda: {
            0: "underway using engine",
            1: "at anchor",
            2: "not under command",
            3: "restricted maneuverability",
            4: "constrained by draught",
            5: "moored",
            6: "aground",
            7: "engaged in fishing",
            8: "under way sailing",
            14: "ais-sart",
            15: "not defined",
        }
    )
    event_type_names: dict[int, str] = field(
        default_factory=lambda: {
            1: "port_arrival",
            2: "port_departure",
            11: "area_entry",
            12: "area_exit",
            19: "ais_gap_start",
            20: "ais_gap_end",
        }
    )
    monitoring_zones: dict[str, dict[str, float]] = field(default_factory=lambda: dict(MONITORING_ZONES))
