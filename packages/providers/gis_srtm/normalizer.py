"""SRTM elevation normalizer and low-level HGT utilities."""

from __future__ import annotations

import math
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.terrain.models import NormalizedMapLayer


class SRTMNormalizer:
    provider_id = "gis-srtm"

    @staticmethod
    def _provenance(raw_id: str | None = None, confidence: float = 0.98) -> Provenance:
        return Provenance(
            provider_id="gis-srtm",
            provider_name="NASA SRTM",
            fetched_at=datetime.now(timezone.utc),
            raw_id=raw_id,
            confidence=confidence,
            classification="UNCLASSIFIED",
        )

    def normalize_elevation_point(self, lat: float, lon: float, elevation: float) -> NormalizedMapLayer:
        return NormalizedMapLayer(
            layer_type="elevation",
            format="point",
            bounds={"north": lat, "south": lat, "east": lon, "west": lon},
            resolution_m=30,
            tags=[f"elevation_m={round(float(elevation), 2)}"],
            provenance=self._provenance(raw_id=f"{lat:.5f},{lon:.5f}"),
        )

    def normalize_elevation_profile(self, profile: list[dict[str, Any]]) -> NormalizedMapLayer:
        lats = [float(p["lat"]) for p in profile] if profile else [0.0]
        lons = [float(p["lon"]) for p in profile] if profile else [0.0]
        return NormalizedMapLayer(
            layer_type="elevation",
            format="profile",
            bounds={"north": max(lats), "south": min(lats), "east": max(lons), "west": min(lons)},
            resolution_m=30,
            tags=[f"samples={len(profile)}"],
            provenance=self._provenance(raw_id="profile"),
        )

    def normalize_viewshed(self, viewshed: dict[str, Any]) -> NormalizedMapLayer:
        points = viewshed.get("visible_points", []) + viewshed.get("hidden_points", [])
        if points:
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            bounds = {"north": max(lats), "south": min(lats), "east": max(lons), "west": min(lons)}
        else:
            bounds = {"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0}
        return NormalizedMapLayer(
            layer_type="elevation",
            format="viewshed",
            bounds=bounds,
            resolution_m=30,
            tags=[f"visible_area_km2={viewshed.get('visible_area_km2', 0.0)}"],
            provenance=self._provenance(raw_id="viewshed"),
        )

    def tile_name_from_latlon(self, lat: float, lon: float) -> str:
        lat_deg = math.floor(lat)
        lon_deg = math.floor(lon)
        lat_prefix = "N" if lat_deg >= 0 else "S"
        lon_prefix = "E" if lon_deg >= 0 else "W"
        return f"{lat_prefix}{abs(lat_deg):02d}{lon_prefix}{abs(lon_deg):03d}.hgt"

    def read_hgt_tile(self, filepath: str) -> list[list[int | None]]:
        path = Path(filepath)
        payload = path.read_bytes()
        values = array("h")
        values.frombytes(payload)
        if len(values) == 0:
            return []
        values.byteswap()
        size = int(math.sqrt(len(values)))
        grid: list[list[int | None]] = []
        idx = 0
        for _ in range(size):
            row: list[int | None] = []
            for _ in range(size):
                value = int(values[idx])
                row.append(None if value == -32768 else value)
                idx += 1
            grid.append(row)
        return grid

    def bilinear_interpolate(self, grid: list[list[int | float | None]], row_frac: float, col_frac: float) -> float | None:
        if not grid or not grid[0]:
            return None
        r0 = int(math.floor(row_frac))
        c0 = int(math.floor(col_frac))
        r1 = min(r0 + 1, len(grid) - 1)
        c1 = min(c0 + 1, len(grid[0]) - 1)

        q11 = grid[r0][c0]
        q21 = grid[r0][c1]
        q12 = grid[r1][c0]
        q22 = grid[r1][c1]

        dr = row_frac - r0
        dc = col_frac - c0

        weighted = []
        for val, weight in [
            (q11, (1 - dr) * (1 - dc)),
            (q21, (1 - dr) * dc),
            (q12, dr * (1 - dc)),
            (q22, dr * dc),
        ]:
            if val is not None:
                weighted.append((float(val), float(weight)))
        if not weighted:
            return None
        total_w = sum(w for _, w in weighted)
        if total_w <= 0:
            return None
        return sum(v * w for v, w in weighted) / total_w
