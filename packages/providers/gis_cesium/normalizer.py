"""Normalizer for Cesium terrain metadata and 3D tilesets."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.terrain.models import NormalizedMapLayer


class CesiumNormalizer:
    provider_id = "gis-cesium"

    @staticmethod
    def _provenance(raw_id: str | None = None) -> Provenance:
        return Provenance(
            provider_id="gis-cesium",
            provider_name="Cesium ion",
            fetched_at=datetime.now(timezone.utc),
            raw_id=raw_id,
            confidence=0.95,
            classification="UNCLASSIFIED",
        )

    def resolution_from_zoom(self, zoom: int) -> float:
        if zoom <= 12:
            return 30.0
        if zoom >= 16:
            return 2.0
        if zoom == 14:
            return 10.0
        if zoom == 13:
            return 17.0
        if zoom == 15:
            return 5.0
        return max(2.0, 30.0 / (2 ** (zoom - 12)))

    def normalize_terrain_metadata(self, tile_info: dict[str, Any]) -> NormalizedMapLayer:
        zoom = int(tile_info.get("z", 12))
        return NormalizedMapLayer(
            layer_type="elevation",
            format="quantized-mesh",
            bounds=tile_info.get("bounds", {}),
            resolution_m=self.resolution_from_zoom(zoom),
            offline_path=tile_info.get("offline_path"),
            tags=[f"asset={tile_info.get('asset_id', 1)}", f"z{zoom}"],
            provenance=self._provenance(raw_id=f"{tile_info.get('z')}/{tile_info.get('x')}/{tile_info.get('y')}"),
        )

    def _bounds_from_bounding_volume(self, volume: dict[str, Any]) -> dict[str, float]:
        if "sphere" in volume:
            x, y, z, r = volume["sphere"]
            return {"center_x": x, "center_y": y, "center_z": z, "radius_m": r}
        if "box" in volume:
            vals = volume["box"]
            cx, cy, cz = vals[0], vals[1], vals[2]
            hx = math.sqrt(vals[3] ** 2 + vals[4] ** 2 + vals[5] ** 2)
            hy = math.sqrt(vals[6] ** 2 + vals[7] ** 2 + vals[8] ** 2)
            hz = math.sqrt(vals[9] ** 2 + vals[10] ** 2 + vals[11] ** 2)
            return {"center_x": cx, "center_y": cy, "center_z": cz, "half_x": hx, "half_y": hy, "half_z": hz}
        if "region" in volume:
            west, south, east, north, min_h, max_h = volume["region"]
            return {
                "west": math.degrees(west),
                "south": math.degrees(south),
                "east": math.degrees(east),
                "north": math.degrees(north),
                "min_height": min_h,
                "max_height": max_h,
            }
        return {}

    def normalize_3d_tileset(self, tileset: dict[str, Any]) -> NormalizedMapLayer:
        root = tileset.get("root", {})
        bv = root.get("boundingVolume", {})
        content_uri = str(root.get("content", {}).get("uri", "")).lower()
        layer_type = "building" if "building" in content_uri or "osm" in content_uri else "terrain"
        return NormalizedMapLayer(
            layer_type=layer_type,
            format="3dtiles",
            bounds=self._bounds_from_bounding_volume(bv),
            tags=[f"geometric_error={tileset.get('geometricError', 0)}"],
            provenance=self._provenance(raw_id=str(tileset.get("asset", {}).get("id"))),
        )

    def normalize_asset_list(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for asset in assets:
            out.append(
                {
                    "asset_id": asset.get("id"),
                    "name": asset.get("name"),
                    "type": asset.get("type"),
                    "size_mb": round(float(asset.get("bytes", 0)) / (1024 * 1024), 3),
                    "status": asset.get("status", "UNKNOWN"),
                }
            )
        return out
