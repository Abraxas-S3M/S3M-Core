from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.pipelines.terrain.terrain_pipeline import TerrainMappingPipeline


BOUNDS = {"north": 24.9, "south": 24.6, "east": 46.9, "west": 46.5}
ROUTE = [(24.7136, 46.6753), (24.55, 45.8), (23.7, 43.2), (21.4858, 39.1925)]


def test_tactical_map_all_components() -> None:
    out = TerrainMappingPipeline(mode="airgapped").get_tactical_map(BOUNDS, zoom=12)
    assert "map_tiles" in out and "features" in out and "elevation" in out


def test_elevation_along_route() -> None:
    profile = TerrainMappingPipeline(mode="airgapped").get_elevation_along_route(ROUTE)
    assert len(profile) > 0
    assert {"lat", "lon", "elevation_m", "distance_from_start_m"}.issubset(profile[0].keys())


def test_route_line_of_sight() -> None:
    out = TerrainMappingPipeline(mode="airgapped").check_route_line_of_sight(ROUTE, observer_height_m=2.0)
    assert "segments" in out
    assert "fully_visible" in out


def test_viewshed_overlay() -> None:
    out = TerrainMappingPipeline(mode="airgapped").get_viewshed_overlay((24.7136, 46.6753), radius_km=1.0, height_m=2.0)
    assert "visible_points" in out and "hidden_points" in out


def test_offline_package_components() -> None:
    out = TerrainMappingPipeline(mode="airgapped").prepare_offline_package("riyadh_metro")
    assert {"gis-mapbox", "gis-osm", "gis-srtm", "gis-cesium"}.issubset(out["components"].keys())


def test_feed_to_navigation() -> None:
    out = TerrainMappingPipeline(mode="airgapped").feed_to_navigation(ROUTE)
    assert "elevation_profile" in out
    assert "slopes" in out
    assert "road_segments" in out
    assert "obstacles" in out


def test_feed_to_dashboard() -> None:
    out = TerrainMappingPipeline(mode="airgapped").feed_to_dashboard(BOUNDS)
    assert "base_map" in out
    assert "overlays" in out
    assert "elevation_contours" in out


def test_health_check_all_providers() -> None:
    out = TerrainMappingPipeline(mode="airgapped").health_check()
    assert set(out["providers"].keys()) == {"gis-mapbox", "gis-osm", "gis-srtm", "gis-cesium"}
