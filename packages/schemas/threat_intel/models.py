"""Normalized threat-intel schemas for IOC and actor intelligence fusion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List

from ..common.base import BaseNormalizedRecord


@dataclass
class NormalizedThreatIndicator(BaseNormalizedRecord):
    """Unified IOC model consumed by SOC and ThreatManager workflows."""

    indicator_type: str = "ip"
    value: str = ""
    threat_type: str = "unknown"
    severity: str = "low"
    first_seen: datetime | str | None = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime | str | None = field(default_factory=lambda: datetime.now(timezone.utc))
    mitre_techniques: list[str] = field(default_factory=list)
    reputation_score: float = 0.0
    source_feed: str = "unknown"
    tlp: str = "AMBER"
    confidence: float = 0.5
    enrichment: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.indicator_type, str):
            raise ValueError("indicator_type must be text")
        if not isinstance(self.value, str):
            raise ValueError("value must be text")
        if not 0.0 <= self.reputation_score <= 100.0:
            raise ValueError("reputation_score must be between 0 and 100")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        self.indicator_type = self.indicator_type.strip().lower()
        self.value = self.value.strip()
        self.severity = (self.severity or "low").strip().lower()
        if self.severity not in SEVERITY_ORDER:
            self.severity = "low"

        self.reputation_score = float(self.reputation_score)
        self.confidence = float(self.confidence)
        self.mitre_techniques = _dedup_list(self.mitre_techniques)
        self.tags = _dedup_list(self.tags)


SEVERITY_ORDER: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


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


def _dedup_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get((severity or "low").lower(), SEVERITY_ORDER["low"])


def severity_max(a: str, b: str) -> str:
    return a if severity_rank(a) >= severity_rank(b) else b


def severity_min(a: str, b: str) -> str:
    return a if severity_rank(a) <= severity_rank(b) else b


def merge_indicators(base: NormalizedThreatIndicator, other: NormalizedThreatIndicator) -> NormalizedThreatIndicator:
    """Merge two indicator records preserving strongest tactical signal."""

    base_provenance = _to_dict(base.provenance)
    other_provenance = _to_dict(other.provenance)

    merged = NormalizedThreatIndicator(
        indicator_type=base.indicator_type,
        value=base.value,
        threat_type=other.threat_type if other.threat_type != "unknown" else base.threat_type,
        severity=severity_max(base.severity, other.severity),
        first_seen=base.first_seen or other.first_seen,
        last_seen=other.last_seen or base.last_seen,
        mitre_techniques=sorted(set(base.mitre_techniques + other.mitre_techniques)),
        reputation_score=(base.reputation_score + other.reputation_score) / 2.0,
        source_feed=base.source_feed if base.source_feed != "unknown" else other.source_feed,
        tlp=base.tlp or other.tlp,
        tags=sorted(set(base.tags + other.tags)),
        provenance={**base_provenance, **other_provenance},
        confidence=max(base.confidence, other.confidence),
        enrichment={**base.enrichment, **other.enrichment},
    )
    return merged

def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}
