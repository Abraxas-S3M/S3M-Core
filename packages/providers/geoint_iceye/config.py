"""Configuration for ICEYE SAR provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ICEYEConfig:
    base_url: str = "https://api.iceye.com/v1"
    rate_limit_rpm: int = 30
    product_types: dict[str, float] = field(default_factory=lambda: {
        "spotlight": 0.8,
        "stripmap": 2.5,
        "scan": 5.0,
    })
    analytics_endpoints: dict[str, str] = field(default_factory=lambda: {
        "change_detection": "/analytics/change-detection",
        "flood_mapping": "/analytics/flood-extent",
    })
