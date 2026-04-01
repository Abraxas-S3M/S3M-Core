"""Configuration constants for NASA FIRMS / Earthdata integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS


@dataclass(slots=True)
class NASAEarthdataConfig:
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api"
    cmr_base_url: str = "https://cmr.earthdata.nasa.gov/search"
    firms_default_instrument: str = "VIIRS_SNPP_NRT"
    firms_rate_limit_rpm: int = 10
    cmr_rate_limit_rpm: int = 30
    saudi_region_codes: list[str] = field(default_factory=lambda: ["SAU", "YEM", "OMN", "ARE", "KWT", "BHR", "QAT", "IRQ", "IRN"])
    saudi_bbox: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS))
    fire_confidence_threshold: str = "nominal"
