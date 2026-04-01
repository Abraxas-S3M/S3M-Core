"""Configuration for OpenStreetMap and Overpass tactical ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field


MILITARY_QUERIES = {
    "roads": 'way["highway"~"motorway|trunk|primary|secondary"]({bbox});',
    "buildings": 'way["building"="yes"]({bbox});',
    "military": 'node["military"]({bbox}); way["military"]({bbox}); relation["military"]({bbox});',
    "airports": 'node["aeroway"="aerodrome"]({bbox}); way["aeroway"="runway"]({bbox});',
    "ports": 'node["harbour"="yes"]({bbox}); way["waterway"="dock"]({bbox});',
    "bridges": 'way["bridge"="yes"]({bbox});',
    "tunnels": 'way["tunnel"="yes"]({bbox});',
    "water": 'way["natural"="water"]({bbox}); relation["natural"="water"]({bbox});',
    "landuse": 'way["landuse"]({bbox});',
    "power": 'way["power"="line"]({bbox}); node["power"="tower"]({bbox});',
    "fuel_stations": 'node["amenity"="fuel"]({bbox});',
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

PBF_DOWNLOADS = {
    "gcc_states": "asia/gcc-states-latest.osm.pbf",
    "saudi_arabia": "asia/saudi-arabia-latest.osm.pbf",
}


@dataclass(slots=True)
class OSMConfig:
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    geofabrik_base: str = "https://download.geofabrik.de"
    rate_limit_rpm: int = 10
    timeout_seconds: int = 60
    pbf_cache_dir: str = "data/integrations/gis-osm/pbf/"
    extract_cache_dir: str = "data/integrations/gis-osm/extracts/"
    military_queries: dict[str, str] = field(default_factory=lambda: dict(MILITARY_QUERIES))
    saudi_bounds: dict[str, dict[str, float]] = field(default_factory=lambda: dict(SAUDI_BOUNDS))
    pbf_downloads: dict[str, str] = field(default_factory=lambda: dict(PBF_DOWNLOADS))
