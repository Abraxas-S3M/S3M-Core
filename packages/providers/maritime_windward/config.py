"""Configuration for Windward maritime AI risk analytics provider."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WindwardConfig:
    base_url: str = "https://api.windward.ai/v2"
    rate_limit_rpm: int = 15
    risk_level_thresholds: dict[str, int] = field(
        default_factory=lambda: {
            "critical": 80,
            "high": 60,
            "medium": 30,
            "low": 0,
        }
    )
    risk_indicator_types: list[str] = field(
        default_factory=lambda: [
            "sanctions_proximity",
            "dark_activity",
            "sts_transfer",
            "flag_hopping",
            "identity_manipulation",
            "route_deviation",
            "port_risk",
            "cargo_risk",
        ]
    )
    sanctions_lists: list[str] = field(default_factory=lambda: ["OFAC_SDN", "EU_SANCTIONS", "UN_SANCTIONS"])
    saudi_high_risk_zones: list[str] = field(
        default_factory=lambda: ["bab_el_mandeb", "strait_of_hormuz", "gulf_of_aden"]
    )
