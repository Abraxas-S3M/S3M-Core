"""Normalized threat-intel schemas for IOC and actor intelligence fusion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedThreatIndicator(BaseNormalizedRecord):
    indicator_type: str = "ip"
    value: str = ""
    threat_type: str = "malware"
    severity: str = "low"
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    mitre_techniques: List[str] = field(default_factory=list)
    reputation_score: float = 0.0
    source_feed: str = ""
    tlp: str = "TLP:CLEAR"

    def __post_init__(self) -> None:
        if not 0.0 <= self.reputation_score <= 100.0:
            raise ValueError("reputation_score must be between 0 and 100")


@dataclass
class IOC:
    indicator_type: str
    value: str


@dataclass
class ThreatActor:
    actor_id: str
    name: str
    origin: str


@dataclass
class Campaign:
    campaign_id: str
    name: str
    actor_ids: List[str] = field(default_factory=list)
