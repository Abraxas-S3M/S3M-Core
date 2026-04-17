"""Monitoring primitives for recursive transcript oversight in S3M."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EmotionProfile:
    """Per-turn affect telemetry used for operator-risk assessment."""

    valence: float = 0.0
    arousal: float = 0.0
    stress: float = 0.0
    confidence: float = 0.0
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valence": float(self.valence),
            "arousal": float(self.arousal),
            "stress": float(self.stress),
            "confidence": float(self.confidence),
            "labels": list(self.labels),
        }


@dataclass(slots=True)
class TranscriptTurn:
    """One logged interaction turn with safety and reasoning context."""

    role: str
    content: str
    timestamp: str = field(default_factory=_utc_now_iso)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    sae_features: Dict[int, float] = field(default_factory=dict)
    emotion_profile: Optional[EmotionProfile] = None
    thinking_text: Optional[str] = None
    deliberation_gate_interventions: List[Dict[str, Any]] = field(default_factory=list)
    action_gate_decisions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": list(self.tool_calls),
            "sae_features": {int(k): float(v) for k, v in self.sae_features.items()},
            "emotion_profile": None if self.emotion_profile is None else self.emotion_profile.to_dict(),
            "thinking_text": self.thinking_text,
            "deliberation_gate_interventions": list(self.deliberation_gate_interventions),
            "action_gate_decisions": list(self.action_gate_decisions),
        }


@dataclass(slots=True)
class Transcript:
    """Complete mission-session transcript for post-action review."""

    session_id: str
    turns: List[TranscriptTurn] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turns": [turn.to_dict() for turn in self.turns],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class Summary:
    """Hierarchical summary generated from one transcript."""

    text: str
    depth_levels: int
    chunk_count: int
    concerning_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "depth_levels": int(self.depth_levels),
            "chunk_count": int(self.chunk_count),
            "concerning_flags": list(self.concerning_flags),
        }


@dataclass(slots=True)
class BehaviorReport:
    """Risk report produced by summary-level concern judgment."""

    concern_level: int
    categories: List[str]
    evidence_quotes: List[str]
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concern_level": int(self.concern_level),
            "categories": list(self.categories),
            "evidence_quotes": list(self.evidence_quotes),
            "recommended_action": self.recommended_action,
        }


@dataclass(slots=True)
class BehaviorClassification:
    """Category-level behavior detection from transcript evidence spans."""

    category: str
    confidence: float
    evidence_spans: List[str] = field(default_factory=list)
    severity: str = "benign"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": float(self.confidence),
            "evidence_spans": list(self.evidence_spans),
            "severity": self.severity,
        }


@dataclass(slots=True)
class AlertDecision:
    """Final monitoring alert synthesized across all oversight channels."""

    level: str
    sources: List[str]
    summary: str
    recommended_action: str
    auto_action_taken: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "sources": list(self.sources),
            "summary": self.summary,
            "recommended_action": self.recommended_action,
            "auto_action_taken": self.auto_action_taken,
        }

