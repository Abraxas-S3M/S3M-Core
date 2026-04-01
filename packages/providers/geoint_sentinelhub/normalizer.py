"""Normalization helpers for Sentinel Hub API responses."""

from __future__ import annotations

from typing import Any

from packages.providers._shared import GeoPoint, NormalizedGeoObservation, Provenance


class SentinelHubNormalizer:
    provider_id = "geoint-sentinelhub"

    def normalize_catalog_result(self, feature: dict[str, Any]) -> NormalizedGeoObservation:
        props = feature.get("properties", {})
        bbox = feature.get("bbox") or [0.0, 0.0, 0.0, 0.0]
        lat = (bbox[1] + bbox[3]) / 2
        lon = (bbox[0] + bbox[2]) / 2
        dt = props.get("datetime") or props.get("start_datetime") or "1970-01-01T00:00:00Z"
        return NormalizedGeoObservation(
            observation_id=feature.get("id", "unknown"),
            timestamp=dt,
            provider_id=self.provider_id,
            observation_type="sar" if "sentinel-1" in feature.get("collection", "") else "multispectral",
            satellite=str(props.get("platform", "Sentinel")),
            collection=str(feature.get("collection", "")),
            geo_point=GeoPoint(lat=float(lat), lon=float(lon)),
            bbox=[float(v) for v in bbox],
            bands=[str(v) for v in props.get("instruments", [])],
            tags=["sentinelhub", "catalog"],
            metadata={"stac": feature, "cloud_cover": props.get("eo:cloud_cover", 0)},
            provenance=Provenance(provider_id=self.provider_id, source="sentinelhub-catalog", confidence=0.9),
        )

    def normalize_process_result(self, response_bytes: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"imagery_bytes": response_bytes, "metadata": metadata}

    def normalize_statistics(self, stats: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in stats.get("data", []):
            band = item.get("outputs", {}).get("default", {}).get("bands", {}).get("B0", {})
            s = band.get("stats", {})
            out.append({
                "from": item.get("interval", {}).get("from"),
                "to": item.get("interval", {}).get("to"),
                "min": s.get("min"),
                "max": s.get("max"),
                "mean": s.get("mean"),
                "stdev": s.get("stDev"),
            })
        return out
