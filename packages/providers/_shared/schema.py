"""Normalized schemas for GEOINT provider observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(slots=True)
class Provenance:
    provider_id: str
    source: str
    confidence: float = 0.0
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class NormalizedGeoObservation:
    observation_id: str
    timestamp: str
    provider_id: str
    observation_type: str
    satellite: str
    geo_point: GeoPoint
    collection: str = ""
    resolution_m: float | None = None
    bbox: list[float] | None = None
    bands: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=lambda: Provenance(provider_id="unknown", source="unknown"))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["geo_point"] = {"lat": self.geo_point.lat, "lon": self.geo_point.lon}
        payload["provenance"] = asdict(self.provenance)
        return payload
