"""Normalize Capella SAR catalog and tasking records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.geospatial.models import NormalizedGeoObservation

from .config import CapellaConfig


class CapellaNormalizer:
    def __init__(self, config: CapellaConfig | None = None) -> None:
        self.config = config or CapellaConfig()

    def normalize_scene(self, scene: dict[str, Any]) -> NormalizedGeoObservation:
        collection_type = str(scene.get("collection_type", "spotlight"))
        resolution = self.config.resolution_m.get(collection_type, 0.25)
        geometry = scene.get("geometry", {}) if isinstance(scene.get("geometry"), dict) else {}
        ring = geometry.get("coordinates", [[[]]])[0] if isinstance(geometry, dict) else []
        try:
            lats = [float(p[1]) for p in ring]
            lons = [float(p[0]) for p in ring]
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)
        except Exception:
            lat, lon = 25.0, 50.0

        polarization = scene.get("polarization", ["VV"])
        if not isinstance(polarization, list):
            polarization = [str(polarization)]

        return NormalizedGeoObservation(
            observation_type="sar",
            satellite=str(scene.get("satellite", "Capella")),
            resolution_m=resolution,
            cloud_cover_pct=None,
            bands=["X-band", *[str(pol) for pol in polarization]],
            geo_point=GeoPoint(lat=lat, lon=lon),
            tags=["all_weather", "night_capable", "cloud_penetrating", collection_type, "premium"],
            acquisition_time=datetime.fromisoformat(str(scene.get("acquisition_time", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00")),
            provenance=Provenance(
                provider_id="geoint-capella",
                provider_name="Capella Space",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(scene.get("id", "unknown")),
                confidence=0.97,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_tasking(self, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(order.get("task_id", "")),
            "status": str(order.get("status", "submitted")),
            "collection_type": str(order.get("collection_type", "spotlight")),
            "window_open": str(order.get("window_open", "")),
            "window_close": str(order.get("window_close", "")),
        }
