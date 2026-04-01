"""Configuration for Capella X-band SAR adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS


@dataclass(slots=True)
class CapellaConfig:
    base_url: str = "https://api.capellaspace.com"
    token_url: str = "https://api.capellaspace.com/oauth/token"
    rate_limit_rpm: int = 30
    product_types: list[str] = field(default_factory=lambda: ["SLC", "GEO", "SICD", "SIDD"])
    collection_types: list[str] = field(default_factory=lambda: ["spotlight", "stripmap", "sliding_spotlight"])
    resolution_m: dict[str, float] = field(default_factory=lambda: {"spotlight": 0.25, "stripmap": 1.0, "sliding_spotlight": 0.5})
    saudi_aois: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS) | {"strait_of_hormuz": [55.8, 25.8, 56.7, 26.6]})
