"""Configuration for Maxar SecureWatch/eAPI provider."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS


@dataclass(slots=True)
class MaxarConfig:
    securewatch_url: str = "https://securewatch.maxar.com"
    eapi_url: str = "https://api.maxar.com"
    rate_limit_rpm: int = 60
    satellites: dict[str, dict[str, float | int | list[str]]] = field(default_factory=lambda: {
        "WorldView-3": {"resolution_m": 0.31, "bands": ["PAN", "Coastal", "Blue", "Green", "Yellow", "Red", "Red Edge", "NIR1", "NIR2", "SWIR-1", "SWIR-2", "SWIR-3", "SWIR-4", "SWIR-5", "SWIR-6", "SWIR-7", "SWIR-8"], "revisit_days": 1.0},
        "WorldView-2": {"resolution_m": 0.46, "bands": ["PAN", "Coastal", "Blue", "Green", "Yellow", "Red", "Red Edge", "NIR1", "NIR2"], "revisit_days": 1.1},
        "GeoEye-1": {"resolution_m": 0.41, "bands": ["PAN", "Blue", "Green", "Red", "NIR"], "revisit_days": 2.1},
        "WorldView-1": {"resolution_m": 0.50, "bands": ["PAN"], "revisit_days": 1.7},
    })
    collection_ids: dict[str, str] = field(default_factory=lambda: {
        "wv01": "WorldView-1",
        "wv02": "WorldView-2",
        "wv03": "WorldView-3",
        "ge01": "GeoEye-1",
    })
    saudi_aois: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS))
