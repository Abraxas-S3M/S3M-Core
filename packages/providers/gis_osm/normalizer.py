"""Normalizer for OSM Overpass JSON into tactical map layers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.terrain.models import NormalizedMapLayer


class OSMNormalizer:
    provider_id = "gis-osm"

    @staticmethod
    def _provenance(raw_id: str | None = None) -> Provenance:
        return Provenance(
            provider_id="gis-osm",
            provider_name="OpenStreetMap",
            fetched_at=datetime.now(timezone.utc),
            raw_id=raw_id,
            confidence=0.80,
            classification="UNCLASSIFIED",
        )

    @staticmethod
    def extract_bilingual_names(tags: dict[str, Any]) -> tuple[str | None, str | None]:
        name_en = tags.get("name:en") or tags.get("name")
        name_ar = tags.get("name:ar")
        return name_en, name_ar

    @staticmethod
    def _bounds_from_geometry(geometry: list[dict[str, float]]) -> dict[str, float]:
        if not geometry:
            return {"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0}
        lats = [float(pt["lat"]) for pt in geometry if "lat" in pt]
        lons = [float(pt["lon"]) for pt in geometry if "lon" in pt]
        return {
            "north": max(lats) if lats else 0.0,
            "south": min(lats) if lats else 0.0,
            "east": max(lons) if lons else 0.0,
            "west": min(lons) if lons else 0.0,
        }

    @staticmethod
    def _layer_type_from_tags(tags: dict[str, Any]) -> str:
        if "highway" in tags:
            return "road"
        if tags.get("building") == "yes" or "building" in tags:
            return "building"
        if "military" in tags:
            return "military"
        if "aeroway" in tags:
            return "airport"
        if "harbour" in tags or tags.get("waterway") == "dock":
            return "port"
        if tags.get("natural") == "water" or tags.get("waterway"):
            return "water"
        if "power" in tags or tags.get("bridge") == "yes" or tags.get("tunnel") == "yes":
            return "infrastructure"
        return "feature"

    def normalize_road(self, element: dict[str, Any]) -> dict[str, Any]:
        tags = element.get("tags", {})
        name_en, name_ar = self.extract_bilingual_names(tags)
        geometry = [(pt.get("lon"), pt.get("lat")) for pt in element.get("geometry", [])]
        return {
            "osm_id": element.get("id"),
            "name_en": name_en,
            "name_ar": name_ar,
            "highway_class": tags.get("highway"),
            "surface": tags.get("surface"),
            "lanes": tags.get("lanes"),
            "max_speed": tags.get("maxspeed"),
            "bridge": tags.get("bridge"),
            "tunnel": tags.get("tunnel"),
            "geometry": geometry,
        }

    def normalize_building(self, element: dict[str, Any]) -> dict[str, Any]:
        tags = element.get("tags", {})
        name_en, name_ar = self.extract_bilingual_names(tags)
        return {
            "osm_id": element.get("id"),
            "name_en": name_en,
            "name_ar": name_ar,
            "building_type": tags.get("building", "yes"),
            "levels": tags.get("building:levels"),
            "geometry": [(pt.get("lon"), pt.get("lat")) for pt in element.get("geometry", [])],
        }

    def normalize_feature(self, element: dict[str, Any]) -> NormalizedMapLayer:
        tags = element.get("tags", {})
        name_en, name_ar = self.extract_bilingual_names(tags)
        tag_pairs = [f"{k}={v}" for k, v in list(tags.items())[:12]]
        if name_en:
            tag_pairs.append(f"name_en={name_en}")
        if name_ar:
            tag_pairs.append(f"name_ar={name_ar}")
        return NormalizedMapLayer(
            layer_type=self._layer_type_from_tags(tags),
            format="geojson",
            bounds=self._bounds_from_geometry(element.get("geometry", [])),
            tags=tag_pairs,
            provenance=self._provenance(raw_id=str(element.get("id"))),
        )

    def normalize_batch(self, elements: list[dict[str, Any]]) -> list[NormalizedMapLayer]:
        return [self.normalize_feature(element) for element in elements]
