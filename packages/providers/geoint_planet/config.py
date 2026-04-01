"""Configuration for Planet provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS


@dataclass(slots=True)
class PlanetConfig:
    base_url: str = "https://api.planet.com"
    rate_limit_rpm: int = 60
    item_types: dict[str, dict[str, float | str]] = field(default_factory=lambda: {
        "PSScene": {"resolution_m": 3.0, "coverage": "global_daily", "revisit": "daily"},
        "SkySatScene": {"resolution_m": 0.5, "coverage": "taskable", "revisit": "on_demand"},
        "SkySatCollect": {"resolution_m": 0.5, "coverage": "taskable", "revisit": "on_demand"},
        "Pelican": {"resolution_m": 0.4, "coverage": "taskable", "revisit": "on_demand"},
    })
    product_bundles: list[str] = field(default_factory=lambda: ["analytic_udm2", "visual", "analytic_sr"])
    saudi_aois: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS))
