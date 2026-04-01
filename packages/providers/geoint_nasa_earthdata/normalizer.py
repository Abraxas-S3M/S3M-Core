"""Normalizers for FIRMS thermal detections and Earthdata metadata."""

from __future__ import annotations

from typing import Any

from packages.providers._shared import GeoPoint, NormalizedGeoObservation, Provenance


class NASAEarthdataNormalizer:
    provider_id = "geoint-nasa-earthdata"

    confidence_map = {"low": 0.3, "nominal": 0.7, "high": 0.95}

    def map_confidence(self, value: str) -> float:
        return self.confidence_map.get(str(value).lower(), 0.3)

    def map_satellite(self, code: str) -> str:
        if code == "N":
            return "Suomi NPP"
        if code == "1":
            return "NOAA-20"
        return "Terra/Aqua"

    def map_resolution(self, instrument: str) -> float:
        return 1000.0 if "MODIS" in instrument.upper() else 375.0

    def normalize_fire(self, fire_record: dict[str, Any]) -> NormalizedGeoObservation:
        instrument = str(fire_record.get("instrument", "VIIRS_SNPP_NRT"))
        confidence = str(fire_record.get("confidence", "low")).lower()
        daynight = str(fire_record.get("daynight", "U"))
        return NormalizedGeoObservation(
            observation_id=str(fire_record.get("id", fire_record.get("acq_datetime", "unknown"))),
            timestamp=str(fire_record.get("acq_datetime", "1970-01-01T00:00:00Z")),
            provider_id=self.provider_id,
            observation_type="thermal",
            satellite=self.map_satellite(str(fire_record.get("satellite", "N"))),
            collection=instrument,
            geo_point=GeoPoint(lat=float(fire_record["latitude"]), lon=float(fire_record["longitude"])),
            resolution_m=self.map_resolution(instrument),
            tags=["fire", "thermal", "firms", instrument, daynight],
            metadata={
                "frp": float(fire_record.get("frp", 0.0)),
                "bright_ti4": float(fire_record.get("bright_ti4", 0.0)),
                "bright_ti5": float(fire_record.get("bright_ti5", 0.0)),
                "scan": float(fire_record.get("scan", 0.0)),
                "track": float(fire_record.get("track", 0.0)),
            },
            provenance=Provenance(provider_id=self.provider_id, source="nasa-firms", confidence=self.map_confidence(confidence)),
        )

    def normalize_fires_batch(self, fires: list[dict[str, Any]]) -> list[NormalizedGeoObservation]:
        return [self.normalize_fire(item) for item in fires]

    def filter_by_confidence(self, fires: list[dict[str, Any]], min_confidence: str = "nominal") -> list[dict[str, Any]]:
        threshold = self.map_confidence(min_confidence)
        return [f for f in fires if self.map_confidence(str(f.get("confidence", "low"))) >= threshold]
