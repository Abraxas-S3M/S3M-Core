"""
Structured output schema for the S3M quad-engine runtime.

The module defines a typed bridge between raw engine text and mission-safe
structured artifacts that can be reconciled with provenance and auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional


class EngineHealth(str, Enum):
    """Normalized health status for one engine execution."""

    HEALTHY = "HEALTHY"
    NOT_LOADED = "NOT_LOADED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass(slots=True)
class ThreatEntity:
    """Structured threat entity extracted from one engine output."""

    label: str
    category: str = "unknown"
    confidence: float = 0.0
    severity: str = "medium"
    location: Optional[str] = None
    provenance_engine: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            "label": self.label,
            "category": self.category,
            "confidence": self.confidence,
            "severity": self.severity,
            "location": self.location,
            "provenance_engine": self.provenance_engine,
        }


@dataclass(slots=True)
class ActionCandidate:
    """Structured action candidate proposed by one engine."""

    action: str
    confidence: float = 0.0
    priority: int = 5
    action_type: str = "support"
    rationale: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            "action": self.action,
            "confidence": self.confidence,
            "priority": self.priority,
            "action_type": self.action_type,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class EvidenceItem:
    """Evidence fragment supporting threat/action claims."""

    summary: str
    confidence: float = 0.0
    source: str = "engine_text"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            "summary": self.summary,
            "confidence": self.confidence,
            "source": self.source,
            "tags": list(self.tags),
        }


@dataclass(slots=True)
class StateUpdate:
    """One blackboard update proposed by an engine."""

    field_path: str
    value: Any
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            "field_path": self.field_path,
            "value": self.value,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class StructuredEngineOutput:
    """
    Canonical structured output emitted by runtime engine adapters.

    Tactical context:
    - A strict schema allows deterministic conflict resolution and mission
      audit replay even when individual engines differ in wording.
    """

    engine_id: str
    task_id: str
    raw_text: str
    health: EngineHealth = EngineHealth.HEALTHY
    confidence: float = 0.0
    threats: List[ThreatEntity] = field(default_factory=list)
    actions: List[ActionCandidate] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    state_updates: List[StateUpdate] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens_generated: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            "engine_id": self.engine_id,
            "task_id": self.task_id,
            "raw_text": self.raw_text,
            "health": self.health.value,
            "confidence": self.confidence,
            "threats": [item.to_dict() for item in self.threats],
            "actions": [item.to_dict() for item in self.actions],
            "evidence": [item.to_dict() for item in self.evidence],
            "state_updates": [item.to_dict() for item in self.state_updates],
            "latency_ms": self.latency_ms,
            "tokens_generated": self.tokens_generated,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


_THREAT_KEYWORDS = {
    "enemy": ("hostile_force", "high"),
    "hostile": ("hostile_force", "high"),
    "ambush": ("ambush", "high"),
    "missile": ("air_threat", "high"),
    "drone": ("air_threat", "medium"),
    "ied": ("explosive_threat", "high"),
    "sniper": ("precision_fire", "high"),
    "armor": ("armored_threat", "medium"),
    "artillery": ("indirect_fire", "high"),
}

_DEFENSIVE_ACTIONS = {
    "hold",
    "defend",
    "secure",
    "observe",
    "monitor",
    "fortify",
    "contain",
    "fallback",
}
_OFFENSIVE_ACTIONS = {"engage", "attack", "strike", "assault", "neutralize", "intercept"}
_SUPPORT_ACTIONS = {"resupply", "reroute", "evacuate", "coordinate", "reinforce"}

_CONFIDENCE_MARKER = re.compile(
    r"\bconfidence\s*[:=]?\s*(1(?:\.0+)?|0?\.\d+|\d{1,3}%?)\b",
    re.IGNORECASE,
)
_PERCENT_MARKER = re.compile(r"\b(\d{1,3})%\b")
_STATE_UPDATE_MARKER = re.compile(r"\b([a-zA-Z0-9_.-]{3,40})\s*:\s*([^\n;|]{1,120})")


def _normalize_confidence(value: float) -> float:
    """Clamp confidence into [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def _extract_confidence_markers(raw_text: str) -> List[float]:
    """Extract explicit confidence hints from free text."""
    scores: List[float] = []
    for match in _CONFIDENCE_MARKER.findall(raw_text):
        token = match.strip()
        if token.endswith("%"):
            scores.append(_normalize_confidence(float(token[:-1]) / 100.0))
        else:
            value = float(token)
            if value > 1.0:
                scores.append(_normalize_confidence(value / 100.0))
            else:
                scores.append(_normalize_confidence(value))

    for percent in _PERCENT_MARKER.findall(raw_text):
        scores.append(_normalize_confidence(float(percent) / 100.0))

    lowered = raw_text.lower()
    if "high confidence" in lowered:
        scores.append(0.85)
    if "medium confidence" in lowered:
        scores.append(0.65)
    if "low confidence" in lowered:
        scores.append(0.35)
    return scores


def _extract_threats(raw_text: str, engine_id: str, base_confidence: float) -> List[ThreatEntity]:
    """Extract threat entities from keyword cues in legacy text."""
    lowered = raw_text.lower()
    threats: List[ThreatEntity] = []
    seen: set[str] = set()

    for keyword, (category, severity) in _THREAT_KEYWORDS.items():
        if keyword not in lowered:
            continue
        label = keyword
        if label in seen:
            continue
        seen.add(label)
        threats.append(
            ThreatEntity(
                label=label,
                category=category,
                confidence=_normalize_confidence(base_confidence),
                severity=severity,
                provenance_engine=engine_id,
            )
        )
    return threats


def _extract_actions(raw_text: str, base_confidence: float) -> List[ActionCandidate]:
    """Extract action candidates from legacy imperative verbs."""
    lowered = raw_text.lower()
    actions: List[ActionCandidate] = []
    seen: set[str] = set()

    for verb in sorted(_DEFENSIVE_ACTIONS | _OFFENSIVE_ACTIONS | _SUPPORT_ACTIONS):
        if verb not in lowered or verb in seen:
            continue
        seen.add(verb)

        action_type = "support"
        if verb in _DEFENSIVE_ACTIONS:
            action_type = "defensive"
        elif verb in _OFFENSIVE_ACTIONS:
            action_type = "offensive"

        actions.append(
            ActionCandidate(
                action=verb,
                confidence=_normalize_confidence(base_confidence),
                priority=3 if action_type == "defensive" else 5,
                action_type=action_type,
                rationale="Extracted from legacy engine text.",
            )
        )
    return actions


def _extract_evidence(raw_text: str, base_confidence: float) -> List[EvidenceItem]:
    """Extract evidence snippets suitable for mission audit trails."""
    evidence: List[EvidenceItem] = []
    for fragment in re.split(r"[.\n]+", raw_text):
        text = fragment.strip()
        if not text:
            continue
        lowered = text.lower()
        if any(token in lowered for token in ("intel", "sensor", "report", "observed", "because")):
            evidence.append(
                EvidenceItem(
                    summary=text[:220],
                    confidence=_normalize_confidence(base_confidence),
                    source="legacy_text_parser",
                    tags=["legacy-bridge", "audit-evidence"],
                )
            )
    return evidence


def _extract_state_updates(raw_text: str, base_confidence: float) -> List[StateUpdate]:
    """Extract key-value style state updates from free text."""
    updates: List[StateUpdate] = []
    for key, value in _STATE_UPDATE_MARKER.findall(raw_text):
        updates.append(
            StateUpdate(
                field_path=key.strip(),
                value=value.strip(),
                confidence=_normalize_confidence(base_confidence),
            )
        )
    return updates


def parse_raw_text_to_structured(
    raw_text: str,
    *,
    engine_id: str,
    task_id: str,
    health: EngineHealth = EngineHealth.HEALTHY,
    base_confidence: float = 0.55,
    metadata: Optional[Dict[str, Any]] = None,
) -> StructuredEngineOutput:
    """
    Convert legacy free text output into StructuredEngineOutput.

    Tactical context:
    - This parser provides a deterministic bridge during migration so legacy
      text-only engines can still participate in synchronized reconciliation.
    """
    safe_text = (raw_text or "").strip()
    confidence_markers = _extract_confidence_markers(safe_text)
    confidence = base_confidence
    if confidence_markers:
        confidence = sum(confidence_markers) / len(confidence_markers)
    confidence = _normalize_confidence(confidence)

    threats = _extract_threats(safe_text, engine_id=engine_id, base_confidence=confidence)
    actions = _extract_actions(safe_text, base_confidence=confidence)
    evidence = _extract_evidence(safe_text, base_confidence=confidence)
    state_updates = _extract_state_updates(safe_text, base_confidence=confidence)

    if health != EngineHealth.HEALTHY:
        confidence = 0.0
        threats = []
        actions = []
        evidence = []
        state_updates = []

    return StructuredEngineOutput(
        engine_id=engine_id,
        task_id=task_id,
        raw_text=safe_text,
        health=health,
        confidence=confidence,
        threats=threats,
        actions=actions,
        evidence=evidence,
        state_updates=state_updates,
        metadata=dict(metadata or {}),
    )
