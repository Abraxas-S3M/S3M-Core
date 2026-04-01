"""Configuration for the Media Cloud OSINT provider."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.providers.osint_gdelt.config import SAUDI_QUERIES


@dataclass(slots=True)
class MediaCloudConfig:
    base_url: str = "https://api.mediacloud.org/api/v2"
    rate_limit_rpm: int = 40
    default_rows: int = 100
    max_rows: int = 1000
    saudi_search_queries: dict[str, str] = field(default_factory=lambda: dict(SAUDI_QUERIES))
    arabic_media_collection_id: int = 34412282
