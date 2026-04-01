"""Core data models for Phase 19 Intelligence & OSINT Briefings.

These structures standardize military-style intelligence products and
air-gapped OSINT processing artifacts for Saudi-focused operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ReportType(Enum):
    """Standard intelligence product types used by operations centers."""

    SITREP = "SITREP"
    INTSUM = "INTSUM"
    WARNORD = "WARNORD"
    DAILY_BRIEF = "DAILY_BRIEF"
    WEEKLY_ESTIMATE = "WEEKLY_ESTIMATE"
    SPOT_REPORT = "SPOT_REPORT"
    THREAT_ASSESSMENT = "THREAT_ASSESSMENT"
    COUNTRY_BRIEF = "COUNTRY_BRIEF"
    CRISIS_REPORT = "CRISIS_REPORT"
    CUSTOM = "CUSTOM"


class ReportClassification(Enum):
    """Security classifications for dissemination control."""

    UNCLASSIFIED = "UNCLASSIFIED"
    FOUO = "FOUO"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP_SECRET"


class SourceType(Enum):
    """OSINT and intelligence source category taxonomy."""

    NEWS_FEED = "NEWS_FEED"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    GOVERNMENT_REPORT = "GOVERNMENT_REPORT"
    ACADEMIC = "ACADEMIC"
    SATELLITE = "SATELLITE"
    MARITIME_AIS = "MARITIME_AIS"
    CYBER_CTI = "CYBER_CTI"
    SIGNALS_INTEL = "SIGNALS_INTEL"
    HUMAN_INTEL = "HUMAN_INTEL"
    COMMERCIAL_DATA = "COMMERCIAL_DATA"
    OSINT_TOOL = "OSINT_TOOL"


class SourceReliability(Enum):
    """NATO source reliability grades (A-F)."""

    A_RELIABLE = "A_RELIABLE"
    B_USUALLY_RELIABLE = "B_USUALLY_RELIABLE"
    C_FAIRLY_RELIABLE = "C_FAIRLY_RELIABLE"
    D_NOT_USUALLY_RELIABLE = "D_NOT_USUALLY_RELIABLE"
    E_UNRELIABLE = "E_UNRELIABLE"
    F_UNKNOWN = "F_UNKNOWN"


class CrisisSeverity(Enum):
    """Operational crisis severity levels for escalation control."""

    ROUTINE = "ROUTINE"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    CRITICAL = "CRITICAL"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IntelReport:
    """Structured bilingual intelligence report ready for command dissemination."""

    report_id: str
    title: str
    report_type: ReportType
    classification: ReportClassification
    date_time_group: str
    originator: str
    summary_en: str
    summary_ar: str
    body_en: str
    body_ar: str
    regions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    risk_assessment: Optional[dict[str, Any]] = None
    recommendations: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    valid_until: Optional[datetime] = None
    approved_by: Optional[str] = None

    @staticmethod
    def to_dtg(dt: datetime) -> str:
        """Format datetime as military DTG, e.g., 011430ZAPR2026."""
        months = [
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
        ]
        utc_dt = dt.astimezone(timezone.utc)
        return (
            f"{utc_dt.day:02d}{utc_dt.hour:02d}{utc_dt.minute:02d}Z"
            f"{months[utc_dt.month - 1]}{utc_dt.year:04d}"
        )

    def is_expired(self) -> bool:
        """Determine if validity window has elapsed."""
        if self.valid_until is None:
            return False
        return _utc_now() > self.valid_until.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "report_type": self.report_type.value,
            "classification": self.classification.value,
            "date_time_group": self.date_time_group,
            "originator": self.originator,
            "summary_en": self.summary_en,
            "summary_ar": self.summary_ar,
            "body_en": self.body_en,
            "body_ar": self.body_ar,
            "regions": list(self.regions),
            "topics": list(self.topics),
            "sources_used": list(self.sources_used),
            "key_findings": list(self.key_findings),
            "risk_assessment": self.risk_assessment,
            "recommendations": list(self.recommendations),
            "attachments": list(self.attachments),
            "created_at": _iso(self.created_at),
            "valid_until": _iso(self.valid_until),
            "approved_by": self.approved_by,
        }


@dataclass
class IntelSource:
    """Metadata for registered intelligence sources in air-gapped workflows."""

    source_id: str
    name: str
    source_type: SourceType
    reliability: SourceReliability
    regions_covered: list[str]
    topics_covered: list[str]
    language: str
    update_frequency: str
    last_ingestion: Optional[datetime] = None
    items_ingested: int = 0
    data_path: Optional[str] = None
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type.value,
            "reliability": self.reliability.value,
            "regions_covered": list(self.regions_covered),
            "topics_covered": list(self.topics_covered),
            "language": self.language,
            "update_frequency": self.update_frequency,
            "last_ingestion": _iso(self.last_ingestion),
            "items_ingested": int(self.items_ingested),
            "data_path": self.data_path,
            "active": bool(self.active),
        }


@dataclass
class OSINTItem:
    """Single ingested OSINT record enriched for intelligence fusion."""

    item_id: str
    source_id: str
    timestamp: datetime
    title: str
    content: str
    language: str
    url: Optional[str]
    regions: list[str]
    topics: list[str]
    entities: list[dict[str, Any]] = field(default_factory=list)
    sentiment: str = "neutral"
    relevance_score: float = 0.0
    summary: Optional[str] = None
    credibility: str = "possible"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "source_id": self.source_id,
            "timestamp": _iso(self.timestamp),
            "title": self.title,
            "content": self.content,
            "language": self.language,
            "url": self.url,
            "regions": list(self.regions),
            "topics": list(self.topics),
            "entities": list(self.entities),
            "sentiment": self.sentiment,
            "relevance_score": float(self.relevance_score),
            "summary": self.summary,
            "credibility": self.credibility,
        }


@dataclass
class CrisisEvent:
    """Tracked geopolitical crisis with lifecycle timeline."""

    event_id: str
    name: str
    description: str
    severity: CrisisSeverity
    region: str
    started_at: datetime
    last_updated: datetime
    status: str
    risk_score: float
    related_sources: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    impact_assessment: Optional[str] = None

    def add_update(self, description: str, severity_change: Optional[str] = None) -> None:
        now = _utc_now()
        update_entry = {
            "timestamp": _iso(now),
            "description": description,
            "severity": self.severity.value,
            "status": self.status,
        }
        if severity_change:
            update_entry["severity_change"] = severity_change
        self.timeline.append(update_entry)
        self.last_updated = now

    def is_active(self) -> bool:
        return self.status != "resolved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "region": self.region,
            "started_at": _iso(self.started_at),
            "last_updated": _iso(self.last_updated),
            "status": self.status,
            "risk_score": float(self.risk_score),
            "related_sources": list(self.related_sources),
            "timeline": list(self.timeline),
            "impact_assessment": self.impact_assessment,
            "active": self.is_active(),
        }


@dataclass
class WarningIndicator:
    """Threshold-based early warning indicator for strategic monitoring."""

    indicator_id: str
    name: str
    description: str
    region: str
    topic: str
    threshold: float
    current_value: float
    trend: str
    last_triggered: Optional[datetime] = None
    active: bool = True

    def is_triggered(self) -> bool:
        return self.active and self.current_value >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "name": self.name,
            "description": self.description,
            "region": self.region,
            "topic": self.topic,
            "threshold": float(self.threshold),
            "current_value": float(self.current_value),
            "trend": self.trend,
            "last_triggered": _iso(self.last_triggered),
            "active": bool(self.active),
            "triggered": self.is_triggered(),
        }


@dataclass
class DailyBrief:
    """Daily commander brief with regional risks and priority watch items."""

    brief_id: str
    date: str
    classification: ReportClassification
    executive_summary_en: str
    executive_summary_ar: str
    regions: list[dict[str, Any]]
    top_events: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    recommendations: list[str]
    sources_consulted: int
    items_analyzed: int
    generated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "date": self.date,
            "classification": self.classification.value,
            "executive_summary_en": self.executive_summary_en,
            "executive_summary_ar": self.executive_summary_ar,
            "regions": list(self.regions),
            "top_events": list(self.top_events),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "sources_consulted": int(self.sources_consulted),
            "items_analyzed": int(self.items_analyzed),
            "generated_at": _iso(self.generated_at),
        }


@dataclass
class WeeklyEstimate:
    """Weekly strategic estimate with trend and 30-day forecast outlook."""

    estimate_id: str
    week: str
    classification: ReportClassification
    executive_summary_en: str
    executive_summary_ar: str
    regional_assessments: list[dict[str, Any]]
    trend_analysis: dict[str, Any]
    emerging_threats: list[dict[str, Any]]
    forecast_30_day: str
    generated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimate_id": self.estimate_id,
            "week": self.week,
            "classification": self.classification.value,
            "executive_summary_en": self.executive_summary_en,
            "executive_summary_ar": self.executive_summary_ar,
            "regional_assessments": list(self.regional_assessments),
            "trend_analysis": dict(self.trend_analysis),
            "emerging_threats": list(self.emerging_threats),
            "forecast_30_day": self.forecast_30_day,
            "generated_at": _iso(self.generated_at),
        }

