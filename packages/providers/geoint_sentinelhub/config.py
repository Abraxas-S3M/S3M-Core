"""Configuration for Sentinel Hub provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS
from packages.providers.geoint_sentinelhub import evalscripts


@dataclass(slots=True)
class SentinelHubConfig:
    base_url: str = "https://services.sentinel-hub.com"
    token_url: str = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
    process_url: str = "https://services.sentinel-hub.com/api/v1/process"
    stats_url: str = "https://services.sentinel-hub.com/api/v1/statistics"
    catalog_url: str = "https://services.sentinel-hub.com/api/v1/catalog/1.0.0/search"
    batch_url: str = "https://services.sentinel-hub.com/api/v1/batch/process"
    default_output_width: int = 512
    default_output_height: int = 512
    default_format: str = "image/png"
    rate_limit_rpm: int = 120
    evalscripts: dict[str, str] = field(default_factory=lambda: {
        "sar_ship_enhancement": evalscripts.SAR_SHIP_ENHANCEMENT,
        "true_color_s2": evalscripts.TRUE_COLOR_S2,
        "ndvi": evalscripts.NDVI,
        "ndwi": evalscripts.NDWI,
        "dust_aerosol": evalscripts.DUST_AEROSOL,
        "thermal_hotspot": evalscripts.THERMAL_HOTSPOT,
    })
    saudi_aois: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS))
