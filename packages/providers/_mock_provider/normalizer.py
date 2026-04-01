"""Mock provider normalizer for geospatial observations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.geospatial.models import NormalizedGeoObservation

from integration_sdk.base.normalizer import BaseNormalizer


class MockNormalizer(BaseNormalizer):
    """Convert mock satellite payloads into normalized geospatial observations."""

    def __init__(self, provider_id: str = "mock-satellite", provider_name: str = "Mock Satellite Provider") -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name

    def normalize(self, raw_data: Dict[str, Any]) -> List[NormalizedGeoObservation]:
        fetched_at = datetime.now(timezone.utc)
        records: List[NormalizedGeoObservation] = []
        for item in raw_data.get("observations", []):
            provenance = Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=fetched_at,
                raw_id=item.get("id"),
                confidence=float(item.get("confidence", 0.9)),
                classification=item.get("classification", "UNCLASSIFIED"),
            )

            footprint = [
                GeoPoint(lat=float(c[0]), lon=float(c[1]))
                for c in item.get("footprint", [])
                if isinstance(c, list) and len(c) == 2
            ]

            observation = NormalizedGeoObservation(
                provenance=provenance,
                timestamp=datetime.fromisoformat(item.get("timestamp")),
                geo_point=GeoPoint(
                    lat=float(item.get("center", {}).get("lat", 0.0)),
                    lon=float(item.get("center", {}).get("lon", 0.0)),
                ),
                tags=item.get("tags", []),
                raw_data_ref=item.get("raw_data_ref"),
                observation_type=item.get("observation_type", "optical"),
                satellite=item.get("satellite", "mock-sat-1"),
                resolution_m=float(item.get("resolution_m", 1.0)),
                cloud_cover_pct=item.get("cloud_cover_pct"),
                footprint=footprint,
                imagery_url=item.get("imagery_url"),
                bands=item.get("bands", []),
                acquisition_time=datetime.fromisoformat(item.get("acquisition_time")),
            )
            records.append(observation)

        return records
