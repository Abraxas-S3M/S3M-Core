"""Configuration for Google Earth Engine GEOINT adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers._shared import GEOINT_SAUDI_AOIS


COLLECTIONS = {
    "sentinel1_sar": "COPERNICUS/S1_GRD",
    "sentinel2_optical": "COPERNICUS/S2_SR_HARMONIZED",
    "viirs_nighttime": "NASA/VIIRS/002/VNP46A2",
    "modis_temperature": "MODIS/061/MOD11A1",
    "surface_water": "JRC/GSW1_4/GlobalSurfaceWater",
    "srtm_elevation": "USGS/SRTMGL1_003",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
}


@dataclass(slots=True)
class GEEConfig:
    rest_api_url: str = "https://earthengine.googleapis.com/v1"
    auth_type: str = "service_account"
    rate_limit_rpm: int = 20
    collections: dict[str, str] = field(default_factory=lambda: dict(COLLECTIONS))
    export_dir: str = "data/integrations/geoint-gee/exports/"
    saudi_regions: dict[str, list[float]] = field(default_factory=lambda: dict(GEOINT_SAUDI_AOIS))
