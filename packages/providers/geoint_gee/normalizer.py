"""Normalization logic for GEE exports and derived analytic products."""

from __future__ import annotations

from typing import Any

from packages.providers._shared import GeoPoint, NormalizedGeoObservation, Provenance


class GEENormalizer:
    provider_id = "geoint-gee"

    collection_to_type = {
        "COPERNICUS/S1_GRD": "sar",
        "COPERNICUS/S2_SR_HARMONIZED": "multispectral",
        "NASA/VIIRS/002/VNP46A2": "nighttime_radiance",
        "MODIS/061/MOD11A1": "thermal",
        "USGS/SRTMGL1_003": "elevation",
        "JRC/GSW1_4/GlobalSurfaceWater": "water",
        "LANDSAT/LC09/C02/T1_L2": "multispectral",
    }

    collection_resolution = {
        "COPERNICUS/S1_GRD": 10.0,
        "COPERNICUS/S2_SR_HARMONIZED": 10.0,
        "NASA/VIIRS/002/VNP46A2": 500.0,
        "MODIS/061/MOD11A1": 1000.0,
        "USGS/SRTMGL1_003": 30.0,
        "JRC/GSW1_4/GlobalSurfaceWater": 30.0,
        "LANDSAT/LC09/C02/T1_L2": 30.0,
    }

    def normalize_export_metadata(self, metadata: dict[str, Any]) -> NormalizedGeoObservation:
        collection = str(metadata.get("collection", "COPERNICUS/S2_SR_HARMONIZED"))
        obs_type = self.collection_to_type.get(collection, "geospatial")
        center = metadata.get("center", {"lat": 24.5, "lon": 46.7})
        return NormalizedGeoObservation(
            observation_id=str(metadata.get("filename", "gee-export")),
            timestamp=str(metadata.get("generated_at", metadata.get("date_range", {}).get("to", "1970-01-01T00:00:00Z"))),
            provider_id=self.provider_id,
            observation_type=obs_type,
            satellite=collection.split("/")[0],
            collection=collection,
            geo_point=GeoPoint(lat=float(center.get("lat", 0.0)), lon=float(center.get("lon", 0.0))),
            resolution_m=self.collection_resolution.get(collection, 30.0),
            bands=list(metadata.get("bands", [])),
            tags=["gee", obs_type, metadata.get("aoi", "unknown")],
            metadata=metadata,
            provenance=Provenance(provider_id=self.provider_id, source="gee-export", confidence=0.8),
        )

    def normalize_change_detection(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "baseline_date": result.get("baseline_date"),
            "current_date": result.get("current_date"),
            "change_magnitude": result.get("change_magnitude"),
            "changed_area_km2": result.get("changed_area_km2"),
            "change_type": result.get("change_type", "unknown"),
        }

    def normalize_nighttime_lights(self, result: dict[str, Any]) -> dict[str, Any]:
        lit = result.get("lit_area_km2", result.get("lit_area", 0.0))
        dark = result.get("dark_area_km2", result.get("dark_area", 0.0))
        return {
            "radiance_mean": result.get("radiance_mean", 0.0),
            "radiance_max": result.get("radiance_max", 0.0),
            "lit_area_km2": lit,
            "dark_area_km2": dark,
            "lit_area": lit,
            "dark_area": dark,
            "change_from_baseline_pct": result.get("change_from_baseline_pct", 0.0),
        }
