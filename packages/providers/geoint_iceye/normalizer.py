"""Normalize ICEYE SAR scenes and analytics responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.geospatial.models import NormalizedGeoObservation

from .config import ICEYEConfig


class ICEYENormalizer:
    def __init__(self, config: ICEYEConfig | None = None) -> None:
        self.config = config or ICEYEConfig()

    def normalize_scene(self, scene: dict[str, Any]) -> NormalizedGeoObservation:
        product_type = str(scene.get("product_type", "spotlight"))
        resolution = self.config.product_types.get(product_type, 1.0)
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
            observation_type="sar",
            satellite=str(scene.get("satellite", "ICEYE-X")),
            resolution_m=resolution,
            cloud_cover_pct=None,
            bands=["X-band", str(scene.get("polarization", "VV"))],
            geo_point=GeoPoint(lat=lat, lon=lon),
            tags=["all_weather", "sar", "change_detection_ready", product_type, "premium"],
            acquisition_time=datetime.fromisoformat(str(scene.get("acquisition_time", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00")),
            provenance=Provenance(
                provider_id="geoint-iceye",
                provider_name="ICEYE",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(scene.get("id", "unknown")),
                confidence=0.96,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_change_detection(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "changes": list(data.get("changes", [])),
            "change_area_km2": float(data.get("change_area_km2", 0.0)),
            "change_type": str(data.get("change_type", "vehicle_movement")),
            "confidence": float(data.get("confidence", 0.96)),
        }

    def normalize_flood_mapping(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "flood_extent_km2": float(data.get("flood_extent_km2", 0.0)),
            "flood_polygon": data.get("flood_polygon", {}),
            "severity": str(data.get("severity", "moderate")),
        }
