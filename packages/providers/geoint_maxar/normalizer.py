"""Normalize Maxar premium imagery and terrain responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.geospatial.models import NormalizedGeoObservation
from packages.schemas.terrain.models import NormalizedMapLayer

from .config import MaxarConfig


class MaxarNormalizer:
    def __init__(self, config: MaxarConfig | None = None) -> None:
        self.config = config or MaxarConfig()

    def _satellite_from_collection(self, collection_id: str) -> str:
        return self.config.collection_ids.get(str(collection_id).lower(), str(collection_id or "WorldView-3"))

    def normalize_catalog_result(self, image: dict[str, Any]) -> NormalizedGeoObservation:
        collection_id = str(image.get("collection") or image.get("collection_id") or "wv03").lower()
        satellite = str(image.get("satellite") or self._satellite_from_collection(collection_id))
        specs = self.config.satellites.get(satellite, self.config.satellites["WorldView-3"])

        geometry = image.get("geometry", {}) if isinstance(image.get("geometry"), dict) else {}
        coords = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
        center_lat = float(image.get("center_lat", 0.0))
        center_lon = float(image.get("center_lon", 0.0))
        if not center_lat or not center_lon:
            try:
                ring = coords[0]
                lats = [float(p[1]) for p in ring]
                lons = [float(p[0]) for p in ring]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
            except Exception:
                center_lat, center_lon = 25.0, 50.0

        cloud_cover = float(image.get("cloud_cover", image.get("eo:cloud_cover", 0.0)) or 0.0)
        obs = NormalizedGeoObservation(
            observation_type="optical",
            satellite=satellite,
            resolution_m=float(specs.get("resolution_m", 0.31)),
            cloud_cover_pct=cloud_cover,
            bands=[str(b) for b in specs.get("bands", [])],
            geo_point=GeoPoint(lat=center_lat, lon=center_lon),
            tags=[
                satellite,
                f"cloud_cover:{cloud_cover}",
                "defense_grade",
                "premium",
            ],
            acquisition_time=datetime.fromisoformat(str(image.get("acquisition_time", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00")),
            provenance=Provenance(
                provider_id="geoint-maxar",
                provider_name="Maxar",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(image.get("id", "unknown")),
                confidence=0.98,
                classification="UNCLASSIFIED",
            ),
        )
        obs.raw_data_ref = str(image.get("id", ""))
        return obs

    def normalize_tasking_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": str(order.get("order_id", "")),
            "estimated_collection_date": str(order.get("estimated_collection_date", "")),
            "sensor": str(order.get("sensor", "WV03")),
            "status": str(order.get("status", "submitted")),
            "priority": str(order.get("priority", "standard")),
        }

    def normalize_3d_terrain(self, metadata: dict[str, Any]) -> NormalizedMapLayer:
        bounds = metadata.get("bounds") if isinstance(metadata.get("bounds"), dict) else {}
        return NormalizedMapLayer(
            layer_type="terrain",
            format=str(metadata.get("format", "terrain")),
            bounds={
                "west": float(bounds.get("west", 0.0)),
                "south": float(bounds.get("south", 0.0)),
                "east": float(bounds.get("east", 0.0)),
                "north": float(bounds.get("north", 0.0)),
            },
            resolution_m=float(metadata.get("resolution_m", 0.5)),
            tile_url_template=str(metadata.get("tile_url_template", "")),
            offline_path=str(metadata.get("offline_path", "")),
            tags=["terrain", "defense_grade", "premium", "maxar-3d"],
            provenance=Provenance(
                provider_id="geoint-maxar",
                provider_name="Maxar",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(metadata.get("tile_id", "unknown")),
                confidence=0.98,
                classification="UNCLASSIFIED",
            ),
        )
