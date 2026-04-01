"""Geospatial utility processing for maritime domain awareness."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Sequence, Tuple


class GeospatialProcessor:
    """Offline geospatial helpers for tactical maritime analytics."""

    EARTH_RADIUS_KM = 6371.0

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in kilometers between two WGS84 points."""
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2.0) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2.0) ** 2
        )
        return 2.0 * self.EARTH_RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, a))))

    def point_in_polygon(self, lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
        """Ray-casting polygon inclusion test for border patrol zones."""
        x = lon
        y = lat
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        for i in range(n):
            lat_i, lon_i = polygon[i]
            lat_j, lon_j = polygon[(i - 1) % n]
            xi = lon_i
            yi = lat_i
            xj = lon_j
            yj = lat_j
            if (yi > y) != (yj > y):
                cross_x = (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
                if x < cross_x:
                    inside = not inside
        return inside

    def compute_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Bearing from point 1 to point 2 in degrees."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        x = math.sin(delta_lon) * math.cos(phi2)
        y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon)
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360.0) % 360.0

    def geo_to_local(self, lat: float, lon: float, origin_lat: float, origin_lon: float) -> Tuple[float, float]:
        """Approximate conversion to local tangent plane (meters)."""
        x = math.radians(lon - origin_lon) * self.EARTH_RADIUS_KM * 1000.0 * math.cos(math.radians(origin_lat))
        y = math.radians(lat - origin_lat) * self.EARTH_RADIUS_KM * 1000.0
        return (x, y)

    def local_to_geo(self, x: float, y: float, origin_lat: float, origin_lon: float) -> Tuple[float, float]:
        """Reverse local tangent plane conversion to WGS84 coordinates."""
        lat = origin_lat + math.degrees(y / (self.EARTH_RADIUS_KM * 1000.0))
        lon = origin_lon + math.degrees(
            x / (self.EARTH_RADIUS_KM * 1000.0 * math.cos(math.radians(origin_lat)))
        )
        return (lat, lon)

    def create_geojson_feature(
        self,
        position: Sequence[float] | Sequence[Sequence[float]],
        properties: Dict[str, Any],
        geometry_type: str = "Point",
    ) -> Dict[str, Any]:
        """Create a GeoJSON Feature for downstream COP overlays."""
        if geometry_type == "Point":
            if len(position) != 2:
                raise ValueError("Point geometry requires [lon, lat]")
            coordinates: Any = [float(position[0]), float(position[1])]
        else:
            coordinates = position
        return {
            "type": "Feature",
            "geometry": {"type": geometry_type, "coordinates": coordinates},
            "properties": dict(properties),
        }

    def export_geojson(self, features: List[Dict[str, Any]], filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        payload = {"type": "FeatureCollection", "features": features}
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def load_geojson(self, filepath: str) -> List[Dict[str, Any]]:
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("type") != "FeatureCollection":
            raise ValueError("GeoJSON must be a FeatureCollection")
        features = payload.get("features", [])
        if not isinstance(features, list):
            raise ValueError("GeoJSON features must be a list")
        return features
