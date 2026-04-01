"""Base normalized record models for tactical data fusion pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4


@dataclass
class GeoPoint:
    lat: float
    lon: float
    alt_m: Optional[float] = None
    crs: str = "EPSG:4326"


@dataclass
class TimeRange:
    start: datetime
    end: datetime


@dataclass
class Provenance:
    provider_id: str
    provider_name: str
    fetched_at: datetime
    raw_id: Optional[str]
    confidence: float
    classification: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class BaseNormalizedRecord:
    record_id: str = field(default_factory=lambda: str(uuid4()))
    provenance: Provenance = field(default_factory=lambda: Provenance(
        provider_id="unknown",
        provider_name="unknown",
        fetched_at=datetime.now(timezone.utc),
        raw_id=None,
        confidence=0.0,
        classification="UNCLASSIFIED",
    ))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    geo_point: Optional[GeoPoint] = None
    tags: List[str] = field(default_factory=list)
    raw_data_ref: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
