"""Configuration for Copernicus (ESA Sentinel) provider.

Tactical context:
- Pre-defines Saudi-relevant maritime and strategic AOIs so operators can
  run deterministic GEOINT pulls for maritime surveillance and border-aware
  monitoring in denied or disconnected environments.
"""

from dataclasses import dataclass, field
from typing import Dict


SAUDI_AOIS = {
    "persian_gulf": "POLYGON((48 24, 56 24, 56 30, 48 30, 48 24))",
    "red_sea": "POLYGON((32 12, 44 12, 44 28, 32 28, 32 12))",
    "red_sea_north": "POLYGON((34 25, 37 25, 37 28, 34 28, 34 25))",
    "bab_el_mandeb": "POLYGON((42 12, 44 12, 44 15, 42 15, 42 12))",
    "strait_of_hormuz": "POLYGON((55 25, 57 25, 57 27, 55 27, 55 25))",
    "gulf_of_aden": "POLYGON((44 11, 48 11, 48 14, 44 14, 44 11))",
    "full_saudi": "POLYGON((34 16, 56 16, 56 32, 34 32, 34 16))",
    "jubail_coast": "POLYGON((49.5 26.8, 49.8 26.8, 49.8 27.2, 49.5 27.2, 49.5 26.8))",
}


@dataclass
class CopernicusConfig:
    """Copernicus provider runtime configuration."""

    base_url: str = "https://catalogue.dataspace.copernicus.eu"
    odata_url: str = "https://catalogue.dataspace.copernicus.eu/odata/v1"
    token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    download_url: str = "https://download.dataspace.copernicus.eu"
    default_collection: str = "SENTINEL-1"
    default_product_type: str = "GRD"
    max_results: int = 20
    rate_limit_rpm: int = 30
    timeout_seconds: int = 60
    saudi_aoi: Dict[str, str] = field(default_factory=lambda: dict(SAUDI_AOIS))
