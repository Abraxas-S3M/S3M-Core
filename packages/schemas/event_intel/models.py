"""Normalized event-intel schemas for global monitoring and alerting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedGlobalEvent(BaseNormalizedRecord):
    event_type: str = "conflict"
    actors: List[str] = field(default_factory=list)
    fatalities: Optional[int] = None
    country: str = ""
    region: str = ""
    source_count: int = 0
    sentiment_score: float = 0.0
    goldstein_scale: Optional[float] = None
    language: str = "en"

    def __post_init__(self) -> None:
        if not -1.0 <= self.sentiment_score <= 1.0:
            raise ValueError("sentiment_score must be between -1 and 1")


@dataclass
class ConflictEvent:
    event_id: str
    conflict_type: str


@dataclass
class MediaEvent:
    event_id: str
    outlet: str
    headline: str
