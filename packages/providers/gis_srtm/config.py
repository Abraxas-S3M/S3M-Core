"""Configuration for NASA SRTM elevation integration."""

from __future__ import annotations

from dataclasses import dataclass, field


SAUDI_TILES = {
    "lat_range": (15, 33),
    "lon_range": (34, 57),
    "total_tiles": 50,
    "total_size_mb": 1200,
}


@dataclass(slots=True)
class SRTMConfig:
    opentopo_url: str = "https://portal.opentopography.org/API/globaldem"
    hgt_cache_dir: str = "data/integrations/gis-srtm/hgt/"
    rate_limit_rpm: int = 5
    tile_size: int = 3601
    resolution_m: int = 30
    void_value: int = -32768
    saudi_tile_range: dict[str, tuple[int, int] | int] = field(default_factory=lambda: dict(SAUDI_TILES))
