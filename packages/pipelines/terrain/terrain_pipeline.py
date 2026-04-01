"""Unified terrain and tactical mapping pipeline for Phase 6/8/16 consumers."""

from __future__ import annotations

from typing import Any

from packages.providers.gis_cesium.adapter import CesiumAdapter
from packages.providers.gis_mapbox.adapter import MapboxAdapter
from packages.providers.gis_osm.adapter import OSMAdapter
from packages.providers.gis_srtm.adapter import SRTMAdapter


class TerrainMappingPipeline:
    def __init__(self, mode: str = "airgapped") -> None:
        self.mapbox = MapboxAdapter(mode=mode)
        self.osm = OSMAdapter(mode=mode)
        self.srtm = SRTMAdapter(mode=mode)
        self.cesium = CesiumAdapter(mode=mode)

    @staticmethod
    def _flatten_grid(grid: list[list[float]]) -> list[float]:
        return [cell for row in grid for cell in row]

    @staticmethod
    def _bounds_from_route(route: list[tuple[float, float]], pad: float = 0.05) -> dict[str, float]:
        lats = [pt[0] for pt in route]
        lons = [pt[1] for pt in route]
        return {
            "north": max(lats) + pad,
            "south": min(lats) - pad,
            "east": max(lons) + pad,
            "west": min(lons) - pad,
        }

    def get_tactical_map(self, bounds: dict[str, float], zoom: int = 14) -> dict[str, Any]:
        map_tiles = self.mapbox.fetch_tile_range(bounds, min_zoom=zoom, max_zoom=zoom, style="satellite")
        roads = self.osm.fetch_roads(bounds)
        buildings = self.osm.fetch_buildings(bounds)
        military = self.osm.fetch_military_features(bounds)
        infrastructure = self.osm.fetch_infrastructure(bounds)
        elev = self.srtm.get_elevation_grid(bounds, resolution_m=30)
        terrain3d = self.cesium.fetch_terrain_region(bounds, max_zoom=min(12, zoom))

        flat = self._flatten_grid(elev["grid"]) if elev.get("grid") else [0.0]
        return {
            "map_tiles": {
                "source": "mapbox",
                "count": map_tiles.get("tiles_downloaded", 0),
                "style": "satellite",
            },
            "features": {
                "roads": roads.get("count", 0),
                "buildings": buildings.get("count", 0),
                "military": military.get("count", 0),
                "infrastructure": infrastructure.get("count", 0),
            },
            "elevation": {
                "min_m": round(min(flat), 3),
                "max_m": round(max(flat), 3),
                "mean_m": round(sum(flat) / len(flat), 3),
            },
            "terrain_3d_available": terrain3d.get("tiles_cached", 0) > 0,
        }

    def get_elevation_along_route(self, waypoints: list[tuple[float, float]]) -> list[dict[str, Any]]:
        profile = self.srtm.get_elevation_profile(waypoints, num_samples=max(10, len(waypoints) * 10))
        for idx in range(len(profile) - 1):
            d_elev = profile[idx + 1]["elevation_m"] - profile[idx]["elevation_m"]
            d_dist = max(1.0, profile[idx + 1]["distance_from_start_m"] - profile[idx]["distance_from_start_m"])
            profile[idx]["grade_percent_to_next"] = round((d_elev / d_dist) * 100.0, 3)
        if profile:
            profile[-1]["grade_percent_to_next"] = 0.0
        return profile

    def check_route_line_of_sight(self, route: list[tuple[float, float]], observer_height_m: float = 2.0) -> dict[str, Any]:
        segments = []
        for idx in range(len(route) - 1):
            los = self.srtm.check_line_of_sight(route[idx], route[idx + 1], height_a_m=observer_height_m, height_b_m=0.0)
            segments.append(
                {
                    "from": route[idx],
                    "to": route[idx + 1],
                    "visible": los["visible"],
                    "max_obstruction_m": los["max_obstruction_m"],
                }
            )
        return {"segments": segments, "fully_visible": all(seg["visible"] for seg in segments) if segments else True}

    def get_viewshed_overlay(self, observer: tuple[float, float], radius_km: float = 10.0, height_m: float = 2.0) -> dict[str, Any]:
        viewshed = self.srtm.compute_viewshed(observer[0], observer[1], observer_height_m=height_m, radius_km=radius_km)
        return {
            "observer": observer,
            "radius_km": radius_km,
            "visible_points": viewshed["visible_points"],
            "hidden_points": viewshed["hidden_points"],
            "visible_area_km2": viewshed["visible_area_km2"],
        }

    def prepare_offline_package(self, region: str = "full_saudi") -> dict[str, Any]:
        mapbox_meta = self.mapbox.generate_offline_pack(region=region, max_zoom=14)
        osm_meta = self.osm.download_pbf(region="saudi_arabia")
        srtm_meta = self.srtm.download_saudi_coverage()
        cesium_meta = self.cesium.generate_offline_terrain(region=region, max_zoom=12)

        components = {
            "gis-mapbox": mapbox_meta.get("size_mb", 0.0),
            "gis-osm": osm_meta.get("size_mb", 0.0),
            "gis-srtm": srtm_meta.get("total_size_mb", 0.0),
            "gis-cesium": cesium_meta.get("size_mb", 0.0),
        }
        return {
            "total_size_mb": round(sum(float(v) for v in components.values()), 3),
            "components": components,
            "mbtiles_path": mapbox_meta.get("mbtiles_path"),
            "pbf_path": osm_meta.get("pbf_path"),
            "hgt_count": srtm_meta.get("tiles_downloaded", 0),
            "terrain_tiles": cesium_meta.get("tile_count", 0),
        }

    def feed_to_navigation(self, route: list[tuple[float, float]]) -> dict[str, Any]:
        elevation_profile = self.get_elevation_along_route(route)
        slopes = [self.srtm.compute_slope(lat, lon) for lat, lon in route]
        bounds = self._bounds_from_route(route)
        roads = self.osm.fetch_roads(bounds)
        los = self.check_route_line_of_sight(route)

        obstacles = [seg for seg in los["segments"] if not seg["visible"]]
        max_elev = max((item["elevation_m"] for item in elevation_profile), default=0.0)
        return {
            "elevation_profile": elevation_profile,
            "slopes": slopes,
            "road_segments": roads.get("roads", []),
            "obstacles": obstacles,
            "recommended_altitude_m": round(max_elev + 50.0, 2),
        }

    def feed_to_dashboard(self, bounds: dict[str, float]) -> dict[str, Any]:
        tactical = self.get_tactical_map(bounds, zoom=14)
        roads = self.osm.fetch_roads(bounds).get("roads", [])
        buildings = self.osm.fetch_buildings(bounds).get("buildings", [])
        military = self.osm.fetch_military_features(bounds).get("military", [])
        center = ((bounds["north"] + bounds["south"]) / 2.0, (bounds["east"] + bounds["west"]) / 2.0)
        terrain = self.mapbox.query_terrain_at_point(center[0], center[1])

        return {
            "base_map": {
                "style": "satellite_streets",
                "tile_source": "offline_cache" if self.mapbox.is_airgapped else "mapbox_api",
            },
            "overlays": [
                {"name": "roads", "count": len(roads)},
                {"name": "buildings", "count": len(buildings)},
                {"name": "military", "count": len(military)},
            ],
            "elevation_contours": terrain.get("features", []),
            "summary": tactical,
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "providers": {
                "gis-mapbox": self.mapbox.health_check(),
                "gis-osm": self.osm.health_check(),
                "gis-srtm": self.srtm.health_check(),
                "gis-cesium": self.cesium.health_check(),
            },
        }
