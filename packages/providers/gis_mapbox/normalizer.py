"""Mapbox response normalization into S3M terrain schema."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.terrain.models import NormalizedMapLayer


class MapboxNormalizer:
    provider_id = "gis-mapbox"

    @staticmethod
    def _provenance(raw_id: str | None = None, confidence: float = 0.95) -> Provenance:
        return Provenance(
            provider_id="gis-mapbox",
            provider_name="Mapbox",
            fetched_at=datetime.now(timezone.utc),
            raw_id=raw_id,
            confidence=confidence,
            classification="UNCLASSIFIED",
        )

    def zoom_to_resolution_m(self, zoom: int) -> float:
        return round(156543.03392804097 / (2**int(zoom)), 2)

    def tile_bounds_from_zxy(self, z: int, x: int, y: int) -> dict[str, float]:
        n = 2**z
        west = x / n * 360.0 - 180.0
        east = (x + 1) / n * 360.0 - 180.0
        north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        return {"north": north, "south": south, "east": east, "west": west}

    def normalize_tile_metadata(self, tile_info: dict[str, Any]) -> NormalizedMapLayer:
        fmt = str(tile_info.get("format", "mvt")).lower()
        layer_type = "vector" if fmt in {"mvt", "pbf"} else "raster"
        z = int(tile_info.get("z", 0))
        x = int(tile_info.get("x", 0))
        y = int(tile_info.get("y", 0))
        return NormalizedMapLayer(
            layer_type=layer_type,
            format="mvt" if fmt in {"mvt", "pbf"} else fmt,
            bounds=self.tile_bounds_from_zxy(z, x, y),
            resolution_m=self.zoom_to_resolution_m(z),
            tile_url_template=tile_info.get("tile_url_template"),
            offline_path=tile_info.get("offline_path"),
            tags=[str(tile_info.get("style", "satellite")), f"z{z}"],
            provenance=self._provenance(raw_id=f"{z}/{x}/{y}"),
        )

    def normalize_geocode_result(self, feature: dict[str, Any]) -> dict[str, Any]:
        props = feature.get("properties", {})
        center = feature.get("center") or [None, None]
        return {
            "place_name_en": props.get("name_en") or feature.get("text_en") or feature.get("text"),
            "place_name_ar": props.get("name_ar") or feature.get("text_ar"),
            "coordinates": [center[0], center[1]],
            "place_type": (feature.get("place_type") or [None])[0],
            "country": "SA",
        }

    def normalize_route(self, route: dict[str, Any]) -> dict[str, Any]:
        distance_m = float(route.get("distance", route.get("distance_m", 0.0)))
        duration_s = float(route.get("duration", route.get("duration_s", 0.0)))
        geometry = route.get("geometry", {})
        coords = geometry.get("coordinates", route.get("geometry", [])) if isinstance(geometry, dict) else route.get("geometry", [])
        return {
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "distance_km": round(distance_m / 1000.0, 2),
            "duration_min": round(duration_s / 60.0, 2),
            "waypoints": [tuple(point) for point in coords],
            "geometry_geojson": {"type": "LineString", "coordinates": coords},
        }

    def estimate_download_size(self, bounds: dict[str, float], min_zoom: int, max_zoom: int) -> dict[str, float]:
        tile_count = 0
        for z in range(int(min_zoom), int(max_zoom) + 1):
            n = 2**z
            x1 = int((bounds["west"] + 180.0) / 360.0 * n)
            x2 = int((bounds["east"] + 180.0) / 360.0 * n)
            lat_n = math.radians(bounds["north"])
            lat_s = math.radians(bounds["south"])
            y1 = int((1.0 - math.log(math.tan(lat_n) + (1 / math.cos(lat_n))) / math.pi) / 2.0 * n)
            y2 = int((1.0 - math.log(math.tan(lat_s) + (1 / math.cos(lat_s))) / math.pi) / 2.0 * n)
            tile_count += (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1)
        return {"tile_count": tile_count, "estimated_mb": round(tile_count * 0.05, 2)}
