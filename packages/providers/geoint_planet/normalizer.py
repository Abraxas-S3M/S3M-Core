"""Normalize Planet scenes, orders, and basemap mosaics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.geospatial.models import NormalizedGeoObservation
from packages.schemas.terrain.models import NormalizedMapLayer

from .config import PlanetConfig


class PlanetNormalizer:
    def __init__(self, config: PlanetConfig | None = None) -> None:
        self.config = config or PlanetConfig()

    def normalize_scene(self, scene: dict[str, Any]) -> NormalizedGeoObservation:
        item_type = str(scene.get("item_type", "PSScene"))
        if item_type == "SkySatCollect":
            item_type = "SkySatScene"
        specs = self.config.item_types.get(item_type, self.config.item_types["PSScene"])
        geometry = scene.get("geometry", {}) if isinstance(scene.get("geometry"), dict) else {}
        ring = geometry.get("coordinates", [[[]]])[0] if isinstance(geometry, dict) else []
        try:
            lats = [float(p[1]) for p in ring]
            lons = [float(p[0]) for p in ring]
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)
        except Exception:
            lat, lon = 25.0, 50.0

        return NormalizedGeoObservation(
            observation_type="optical",
            satellite=str(scene.get("satellite", scene.get("instrument", item_type))),
            resolution_m=float(specs.get("resolution_m", 3.0)),
            cloud_cover_pct=float(scene.get("cloud_cover", 0.0) or 0.0),
            bands=["RGB", "NIR"],
            geo_point=GeoPoint(lat=lat, lon=lon),
            tags=["premium", "planet", item_type, str(scene.get("satellite", "unknown"))],
            acquisition_time=datetime.fromisoformat(str(scene.get("acquired", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00")),
            provenance=Provenance(
                provider_id="geoint-planet",
                provider_name="Planet",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(scene.get("id", "unknown")),
                confidence=0.95,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": str(order.get("order_id", order.get("id", ""))),
            "status": str(order.get("status", "submitted")),
            "item_type": str(order.get("item_type", "PSScene")),
            "product_bundle": str(order.get("product_bundle", "analytic_udm2")),
            "delivery": order.get("delivery", {}),
        }

    def normalize_basemap(self, mosaic: dict[str, Any]) -> NormalizedMapLayer:
        bounds = mosaic.get("bounds", {}) if isinstance(mosaic.get("bounds"), dict) else {}
        return NormalizedMapLayer(
            layer_type="basemap",
            format=str(mosaic.get("format", "tms")),
            bounds={
                "west": float(bounds.get("west", -180.0)),
                "south": float(bounds.get("south", -85.0)),
                "east": float(bounds.get("east", 180.0)),
                "north": float(bounds.get("north", 85.0)),
            },
            resolution_m=float(mosaic.get("resolution_m", 3.0)),
            tile_url_template=str(mosaic.get("tile_url_template", "")),
            offline_path=str(mosaic.get("offline_path", "")),
            tags=["planet", "basemap", "change_detection", "premium"],
            provenance=Provenance(
                provider_id="geoint-planet",
                provider_name="Planet",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(mosaic.get("id", "mosaic")),
                confidence=0.95,
                classification="UNCLASSIFIED",
            ),
        )
