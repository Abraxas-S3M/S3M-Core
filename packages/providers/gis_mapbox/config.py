"""Configuration for Mapbox tactical mapping integration."""

from __future__ import annotations

from dataclasses import dataclass, field


TILE_STYLES = {
    "satellite": "mapbox.satellite-v9",
    "satellite_streets": "mapbox/satellite-streets-v12",
    "dark": "mapbox/dark-v11",
    "outdoors": "mapbox/outdoors-v12",
    "streets": "mapbox/streets-v12",
}

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
class MapboxConfig:
    base_url: str = "https://api.mapbox.com"
    rate_limit_rpm: int = 60
    tile_styles: dict[str, str] = field(default_factory=lambda: dict(TILE_STYLES))
    default_style: str = "satellite_streets"
    offline_cache_dir: str = "data/integrations/gis-mapbox/tiles/"
    mbtiles_dir: str = "data/integrations/gis-mapbox/mbtiles/"
    gazetteer_cache_path: str = "data/integrations/gis-mapbox/gazetteer.json"
    saudi_tile_bounds: dict[str, dict[str, float]] = field(default_factory=lambda: dict(SAUDI_BOUNDS))
    max_zoom_offline: int = 14
    geocoding_countries: str = "SA,YE,OM,AE,KW,BH,QA"
    geocoding_languages: str = "ar,en"
