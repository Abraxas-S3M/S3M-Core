"""Threat detection domain models for S3M Layer 02."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ThreatLevel(IntEnum):
    """Severity scale for tactical prioritization in military operations."""

    INFO = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5

    @classmethod
    def from_value(cls, value: str | int | "ThreatLevel") -> "ThreatLevel":
        """Normalize operator/API input into a ThreatLevel enum."""
        if isinstance(value, ThreatLevel):
            return value
        if isinstance(value, int):
            return ThreatLevel(value)
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in ThreatLevel.__members__:
                return ThreatLevel[normalized]
        raise ValueError(f"Invalid threat level: {value}")


class ThreatSource(str, Enum):
    """Origin of the alert signal entering Layer 02."""

    NETWORK_IDS = "NETWORK_IDS"
    ENDPOINT_SIEM = "ENDPOINT_SIEM"
    OBJECT_DETECTION = "OBJECT_DETECTION"
    ANOMALY_DETECTION = "ANOMALY_DETECTION"
    SENSOR_FUSION = "SENSOR_FUSION"
    MANUAL = "MANUAL"

    @classmethod
    def from_value(cls, value: str | "ThreatSource") -> "ThreatSource":
        if isinstance(value, ThreatSource):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in ThreatSource.__members__:
                return ThreatSource[normalized]
        raise ValueError(f"Invalid threat source: {value}")


class ThreatCategory(str, Enum):
    """Domain category to route military analysis to the right LLM engine."""

    CYBER = "CYBER"
    KINETIC = "KINETIC"
    ELECTRONIC_WARFARE = "ELECTRONIC_WARFARE"
    HYBRID = "HYBRID"
    SURVEILLANCE = "SURVEILLANCE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_value(cls, value: str | "ThreatCategory") -> "ThreatCategory":
        if isinstance(value, ThreatCategory):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in ThreatCategory.__members__:
                return ThreatCategory[normalized]
        raise ValueError(f"Invalid threat category: {value}")


@dataclass
class ThreatEvent:
    """Unified threat alert object exchanged between Layer 02 and Layer 01."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: ThreatSource = ThreatSource.MANUAL
    level: ThreatLevel = ThreatLevel.INFO
    category: ThreatCategory = ThreatCategory.UNKNOWN
    title: str = ""
    description: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    location: Optional[Dict[str, Any]] = None
    asset_ids: List[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    llm_assessment: Optional[str] = None
    classification: str = "UNCLASSIFIED"

    def __post_init__(self) -> None:
        """Validate and normalize fields for secure downstream processing."""
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")

        self.source = ThreatSource.from_value(self.source)
        self.level = ThreatLevel.from_value(self.level)
        self.category = ThreatCategory.from_value(self.category)

        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        if not isinstance(self.raw_data, dict):
            raise ValueError("raw_data must be a dictionary")
        if not isinstance(self.confidence, (float, int)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.confidence = float(self.confidence)
        if self.location is not None and not isinstance(self.location, dict):
            raise ValueError("location must be a dictionary or None")
        if not isinstance(self.asset_ids, list) or any(not isinstance(v, str) for v in self.asset_ids):
            raise ValueError("asset_ids must be a list of strings")
        if not isinstance(self.classification, str) or not self.classification.strip():
            raise ValueError("classification must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to API/export-safe dictionary."""
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        payload["source"] = self.source.value
        payload["level"] = self.level.name
        payload["category"] = self.category.value
        return payload

    def to_prompt(self) -> str:
        """Format alert into a tactical prompt for S3M LLM engines."""
        location_text = self.location if self.location else "N/A"
        assets_text = ", ".join(self.asset_ids) if self.asset_ids else "N/A"
        return (
            "TACTICAL THREAT EVENT\n"
            f"Event ID: {self.event_id}\n"
            f"Timestamp: {self.timestamp.isoformat()}\n"
            f"Source: {self.source.value}\n"
            f"Severity: {self.level.name}\n"
            f"Category: {self.category.value}\n"
            f"Title: {self.title}\n"
            f"Description: {self.description}\n"
            f"Confidence: {self.confidence:.2f}\n"
            f"Location: {location_text}\n"
            f"Affected Assets: {assets_text}\n"
            f"Current Recommendation: {self.recommended_action or 'None'}\n"
            f"Security Classification: {self.classification}\n"
            "Provide concise military analysis and immediate action guidance."
        )


@dataclass
class DetectionResult:
    """Batch output wrapper for one ingestion cycle from a single source."""

    source: ThreatSource
    processing_time_ms: float
    total_events: int
    events_by_level: Dict[str, int]
    events: List[ThreatEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.source = ThreatSource.from_value(self.source)
        if not isinstance(self.processing_time_ms, (int, float)) or self.processing_time_ms < 0:
            raise ValueError("processing_time_ms must be a non-negative number")
        if not isinstance(self.total_events, int) or self.total_events < 0:
            raise ValueError("total_events must be a non-negative integer")
        if not isinstance(self.events_by_level, dict):
            raise ValueError("events_by_level must be a dictionary")
        if not isinstance(self.events, list) or any(not isinstance(e, ThreatEvent) for e in self.events):
            raise ValueError("events must be a list of ThreatEvent")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "processing_time_ms": round(float(self.processing_time_ms), 3),
            "total_events": self.total_events,
            "events_by_level": dict(self.events_by_level),
            "events": [event.to_dict() for event in self.events],
        }
