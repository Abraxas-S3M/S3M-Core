"""Local schema fallbacks for Copernicus provider normalization.

Tactical context:
- Keeps GEOINT normalization deterministic in sovereign deployments even when
  shared integration-sdk schema packages are unavailable in a minimal build.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GeoPoint:
    """Latitude/longitude point for tactical geospatial footprints."""

    lat: float
    lon: float


@dataclass
class Provenance:
    """Lineage metadata for intelligence traceability."""

    provider_id: str
    provider_name: str
    confidence: float
    classification: str


@dataclass
class NormalizedGeoObservation:
    """Canonical GEOINT observation used by S3M analytics pipelines."""

    record_id: str
    observation_type: str
    satellite: str
    resolution_m: Optional[float]
    cloud_cover_pct: Optional[float]
    footprint: List[GeoPoint] = field(default_factory=list)
    acquisition_time: Optional[str] = None
    bands: List[str] = field(default_factory=list)
    provenance: Optional[Provenance] = None
    tags: List[str] = field(default_factory=list)
    raw_data_ref: Optional[str] = None
