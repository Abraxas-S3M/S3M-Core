"""Normalize Copernicus OData products into S3M GEOINT observations.

Tactical context:
- Converts Sentinel catalog metadata into a mission-usable structure consumed
  by maritime detection and geospatial OSINT pipelines in sovereign operations.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from .models import GeoPoint, NormalizedGeoObservation, Provenance


class CopernicusNormalizer:
    """Maps Copernicus product metadata into NormalizedGeoObservation objects."""

    _OBSERVATION_TYPE_MAP = {
        "SENTINEL-1": "sar",
        "SENTINEL-2": "multispectral",
        "SENTINEL-3": "thermal",
        "SENTINEL-5P": "atmospheric",
    }

    _RESOLUTION_MAP = {
        "SENTINEL-1": 10.0,
        "SENTINEL-2": 10.0,
        "SENTINEL-3": 300.0,
        "SENTINEL-5P": 7000.0,
    }

    _BANDS_MAP = {
        "SENTINEL-1": ["VV", "VH"],
        "SENTINEL-2": [
            "B01",
            "B02",
            "B03",
            "B04",
            "B05",
            "B06",
            "B07",
            "B08",
            "B8A",
            "B09",
            "B10",
            "B11",
            "B12",
        ],
        "SENTINEL-3": ["SLSTR", "OLCI", "SRAL"],
        "SENTINEL-5P": ["NO2", "SO2", "O3", "CO", "CH4"],
    }

    def normalize_product(self, product: Dict[str, Any]) -> NormalizedGeoObservation:
        """Normalize one OData product record."""
        product_id = str(product.get("Id") or product.get("id") or "")
        name = str(product.get("Name") or product.get("title") or "unknown")
        collection = self._extract_collection_name(product, name)
        product_type = self._attribute_value(product, "productType") or "unknown"
        aoi_name = str(product.get("_aoi_name") or "unknown")
        cloud_cover = self._extract_cloud_cover(product)
        footprint = self.parse_wkt_polygon(str(product.get("Footprint") or ""))
        acquisition_time = self._safe_nested_get(product, "ContentDate", "Start")
        satellite = self._extract_satellite_name(name, collection)

        return NormalizedGeoObservation(
            record_id=str(uuid.uuid5(uuid.NAMESPACE_URL, product_id or name)),
            observation_type=self._OBSERVATION_TYPE_MAP.get(collection, "unknown"),
            satellite=satellite,
            resolution_m=self._RESOLUTION_MAP.get(collection),
            cloud_cover_pct=cloud_cover,
            footprint=footprint,
            acquisition_time=acquisition_time,
            bands=list(self._BANDS_MAP.get(collection, [])),
            provenance=Provenance(
                provider_id="geoint-copernicus",
                provider_name="Copernicus/ESA",
                confidence=1.0,
                classification="UNCLASSIFIED",
            ),
            tags=["sentinel", collection, product_type, aoi_name],
            raw_data_ref=product.get("_raw_data_ref"),
        )

    def normalize_batch(self, products: List[Dict[str, Any]]) -> List[NormalizedGeoObservation]:
        """Normalize a full list of products."""
        observations: List[NormalizedGeoObservation] = []
        for product in products:
            observations.append(self.normalize_product(product))
        return observations

    def parse_wkt_polygon(self, wkt: str) -> List[GeoPoint]:
        """Parse WKT POLYGON and swap lon/lat to lat/lon GeoPoint."""
        if not wkt:
            return []

        cleaned = wkt.strip()
        if cleaned.startswith("geography'") and ";" in cleaned:
            cleaned = cleaned.split(";", 1)[1]
            if cleaned.endswith("'"):
                cleaned = cleaned[:-1]

        match = re.match(r"POLYGON\s*\(\((.+)\)\)\s*$", cleaned, flags=re.IGNORECASE)
        if not match:
            return []

        raw_points = match.group(1).split(",")
        points: List[GeoPoint] = []
        for raw in raw_points:
            coords = raw.strip().split()
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            points.append(GeoPoint(lat=lat, lon=lon))
        return points

    def _extract_satellite_name(self, product_name: str, collection_name: str) -> str:
        prefix = product_name.split("_", 1)[0] if product_name else ""
        if re.match(r"^S1[AB]$", prefix):
            return f"Sentinel-1{prefix[-1]}"
        if re.match(r"^S2[AB]$", prefix):
            return f"Sentinel-2{prefix[-1]}"
        if re.match(r"^S3[AB]$", prefix):
            return f"Sentinel-3{prefix[-1]}"
        if prefix == "S5P":
            return "Sentinel-5P"
        if collection_name.startswith("SENTINEL-"):
            return collection_name.replace("SENTINEL-", "Sentinel-")
        return "Unknown"

    def _extract_collection_name(self, product: Dict[str, Any], name: str) -> str:
        collection_name = self._safe_nested_get(product, "Collection", "Name")
        if collection_name:
            return str(collection_name)
        if name.startswith("S1"):
            return "SENTINEL-1"
        if name.startswith("S2"):
            return "SENTINEL-2"
        if name.startswith("S3"):
            return "SENTINEL-3"
        if name.startswith("S5P"):
            return "SENTINEL-5P"
        return "UNKNOWN"

    def _attribute_value(self, product: Dict[str, Any], key: str) -> Optional[str]:
        attributes = product.get("Attributes") or []
        for item in attributes:
            if str(item.get("Name", "")).lower() != key.lower():
                continue
            value = item.get("Value")
            if value is None:
                value = item.get("OData.CSC.StringAttribute/Value")
            if value is None:
                value = item.get("OData.CSC.DoubleAttribute/Value")
            if value is not None:
                return str(value)
        return None

    def _extract_cloud_cover(self, product: Dict[str, Any]) -> Optional[float]:
        value = self._attribute_value(product, "cloudCover")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_nested_get(container: Dict[str, Any], key_a: str, key_b: str) -> Optional[str]:
        nested = container.get(key_a)
        if not isinstance(nested, dict):
            return None
        value = nested.get(key_b)
        if value is None:
            return None
        return str(value)
