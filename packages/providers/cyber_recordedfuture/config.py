"""Configuration for Recorded Future provider adapter."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RecordedFutureConfig:
    base_url: str = "https://api.recordedfuture.com/v2"
    rate_limit_rpm: int = 60
    risk_thresholds: dict[str, int] = field(default_factory=lambda: {
        "critical": 80,
        "high": 60,
        "medium": 30,
        "low": 0,
    })
    entity_types: list[str] = field(default_factory=lambda: ["ip", "domain", "hash", "vulnerability", "threatActor"])
