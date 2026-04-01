"""Configuration for Cesium ion terrain and 3D tiles integration."""

from __future__ import annotations

from dataclasses import dataclass, field


SAUDI_BOUNDS = {
    "full_saudi": {"north": 32.2, "south": 15.5, "east": 56.5, "west": 34.5},
    "riyadh_metro": {"north": 25.0, "south": 24.4, "east": 47.1, "west": 46.3},
    "jeddah_metro": {"north": 21.8, "south": 21.2, "east": 39.5, "west": 38.9},
    "eastern_province": {"north": 27.5, "south": 25.0, "east": 51.0, "west": 49.0},
    "yemen_border": {"north": 18.5, "south": 16.0, "east": 48.0, "west": 42.0},
    "red_sea_coast": {"north": 28.0, "south": 20.0, "east": 40.0, "west": 34.0},
    "strait_of_hormuz": {"north": 27.0, "south": 25.0, "east": 57.0, "west": 55.0},
}


@dataclass(slots=True)
class CesiumConfig:
    ion_api_url: str = "https://api.cesium.com/v1"
    assets_url: str = "https://assets.ion.cesium.com"
    rate_limit_rpm: int = 30
    world_terrain_asset_id: int = 1
    osm_buildings_asset_id: int = 3
    terrain_cache_dir: str = "data/integrations/gis-cesium/terrain/"
    tiles_3d_cache_dir: str = "data/integrations/gis-cesium/3dtiles/"
    saudi_bounds: dict[str, dict[str, float]] = field(default_factory=lambda: dict(SAUDI_BOUNDS))
