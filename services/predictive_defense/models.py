"""Data models for predictive defense command-support outputs.

Military context:
These structures represent tactical predictions, swarm assessments, and
operator-facing alerts for offline command-post decision support.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ThreatPosture(str, Enum):
    """Command posture states used in defensive readiness reporting."""

    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


@dataclass
class DefensePrediction:
    """Single track-level prediction for operator awareness."""

    track_id: str
    threat_score: float
    confidence: float
    predicted_intent: str
    horizon_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["threat_score"] = round(float(self.threat_score), 4)
        payload["confidence"] = round(float(self.confidence), 4)
        payload["horizon_seconds"] = int(self.horizon_seconds)
        return payload


@dataclass
class SwarmAnalysis:
    """Summary of potential coordinated hostile swarm behavior."""

    swarm_detected: bool
    track_count: int
    average_threat_score: float
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["average_threat_score"] = round(float(self.average_threat_score), 4)
        return payload


@dataclass
class DefenseCommand:
    """Suggested command action generated from predictive outputs."""

    command_id: str
    track_id: str
    action: str
    priority: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DefenseAlert:
    """Operator alert with posture/severity state for tactical dashboards."""

    alert_id: str
    track_id: str
    posture: ThreatPosture
    severity: str
    message: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        self.posture = ThreatPosture(self.posture)
        self.timestamp = self.timestamp or _utcnow_iso()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["posture"] = self.posture.value
        return payload


@dataclass
class GenomeContext:
    """Validated context payload keyed to a tactical track."""

    track_id: str
    context: Dict[str, Any]
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "context": dict(self.context),
            "updated_at": self.updated_at,
        }

