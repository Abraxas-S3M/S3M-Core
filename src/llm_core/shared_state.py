"""
Thread-safe shared mission state for S3M unified runtime.

The blackboard stores structured engine contributions with provenance, versioning,
and conflict tracking so operational decisions remain auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .engine_output import (
    ActionCandidate,
    EvidenceItem,
    StructuredEngineOutput,
    ThreatEntity,
)


@dataclass(slots=True)
class MissionContext:
    """Mission-level context shared across all engine executions."""

    mission_id: str
    mission_type: str = "general"
    rules_of_engagement: str = "weapons_hold"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable context payload."""
        return {
            "mission_id": self.mission_id,
            "mission_type": self.mission_type,
            "rules_of_engagement": self.rules_of_engagement,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class StateVersion:
    """One immutable state version entry used for mission audit replay."""

    version: int
    reason: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable version record."""
        return {
            "version": self.version,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class EngineContribution:
    """One engine's contribution entry with provenance metadata."""

    contribution_id: str
    engine_id: str
    task_id: str
    confidence: float
    health: str
    fields_written: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable contribution record."""
        return {
            "contribution_id": self.contribution_id,
            "engine_id": self.engine_id,
            "task_id": self.task_id,
            "confidence": self.confidence,
            "health": self.health,
            "fields_written": list(self.fields_written),
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ConflictRecord:
    """Conflict captured when engines write different values to one field."""

    conflict_id: str
    field_path: str
    existing_value: Any
    incoming_value: Any
    existing_engine: str
    incoming_engine: str
    existing_confidence: float
    incoming_confidence: float
    resolution_strategy: str = "PENDING"
    resolved_value: Any = None
    resolved: bool = False
    requires_human_review: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable conflict record."""
        return {
            "conflict_id": self.conflict_id,
            "field_path": self.field_path,
            "existing_value": self.existing_value,
            "incoming_value": self.incoming_value,
            "existing_engine": self.existing_engine,
            "incoming_engine": self.incoming_engine,
            "existing_confidence": self.existing_confidence,
            "incoming_confidence": self.incoming_confidence,
            "resolution_strategy": self.resolution_strategy,
            "resolved_value": self.resolved_value,
            "resolved": self.resolved,
            "requires_human_review": self.requires_human_review,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class DecisionRecord:
    """Authoritative decision artifact emitted after reconciliation."""

    decision_id: str
    mission_id: str
    decision_text: str
    confidence: float
    review_status: str
    selected_action: Optional[str] = None
    selected_threat: Optional[str] = None
    provenance_engines: List[str] = field(default_factory=list)
    rationale: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable decision payload."""
        return {
            "decision_id": self.decision_id,
            "mission_id": self.mission_id,
            "decision_text": self.decision_text,
            "confidence": self.confidence,
            "review_status": self.review_status,
            "selected_action": self.selected_action,
            "selected_threat": self.selected_threat,
            "provenance_engines": list(self.provenance_engines),
            "rationale": list(self.rationale),
            "timestamp": self.timestamp,
        }


class MissionState:
    """
    Versioned, thread-safe blackboard used by the unified runtime.

    Tactical context:
    - Every mutation is versioned for after-action review.
    - Every write is tagged with engine provenance.
    - Field collisions are tracked as explicit conflicts for reconciliation.
    """

    DEFAULT_ENGINE_TRUST: Dict[str, float] = {
        "phi3-mini": 0.84,
        "grok-8b": 0.90,
        "mistral-7b": 0.87,
        "allam-7b": 0.86,
    }

    DEFAULT_DOMAIN_SPECIALISTS: Dict[str, str] = {
        "threat": "grok-8b",
        "actions": "mistral-7b",
        "tactical": "phi3-mini",
        "arabic_nlp": "allam-7b",
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._version = 0
        self._versions: List[StateVersion] = []

        self._context = MissionContext(mission_id="")
        self._threats: Dict[str, ThreatEntity] = {}
        self._actions: Dict[str, ActionCandidate] = {}
        self._evidence: Dict[str, EvidenceItem] = {}
        self._field_values: Dict[str, Any] = {}
        self._field_provenance: Dict[str, Dict[str, Any]] = {}

        self._contributions: List[EngineContribution] = []
        self._conflicts: List[ConflictRecord] = []
        self._decisions: List[DecisionRecord] = []

        self._engine_trust_weights = dict(self.DEFAULT_ENGINE_TRUST)
        self._domain_specialists = dict(self.DEFAULT_DOMAIN_SPECIALISTS)

        self._bump_version("state_initialized")

    @property
    def version(self) -> int:
        """Return current monotonic state version."""
        with self._lock:
            return self._version

    def set_context(self, context: MissionContext) -> None:
        """Set mission context and bump version."""
        with self._lock:
            self._context = context
            self._bump_version("context_updated", {"mission_id": context.mission_id})

    def configure_engine_trust(self, trust_weights: Dict[str, float]) -> None:
        """Override engine trust map used by reconciliation."""
        with self._lock:
            for engine_id, weight in trust_weights.items():
                self._engine_trust_weights[engine_id] = max(0.0, min(1.0, float(weight)))
            self._bump_version("engine_trust_configured")

    def configure_domain_specialists(self, specialists: Dict[str, str]) -> None:
        """Override domain-specialist engine mapping."""
        with self._lock:
            self._domain_specialists.update({k: str(v) for k, v in specialists.items()})
            self._bump_version("domain_specialists_configured")

    def get_engine_trust(self, engine_id: str) -> float:
        """Return trust weight for an engine."""
        with self._lock:
            return float(self._engine_trust_weights.get(engine_id, 0.75))

    def get_domain_specialist(self, domain: str) -> Optional[str]:
        """Return specialist engine identifier for a domain."""
        with self._lock:
            return self._domain_specialists.get(domain)

    def ingest_engine_output(self, output: StructuredEngineOutput) -> EngineContribution:
        """Ingest structured output into shared state with provenance tagging."""
        with self._lock:
            contribution = EngineContribution(
                contribution_id=str(uuid4()),
                engine_id=output.engine_id,
                task_id=output.task_id,
                confidence=float(output.confidence),
                health=output.health.value,
            )

            fields_written: List[str] = []
            for threat in output.threats:
                key = threat.label.strip().lower()
                fields_written.append(f"threats.{key}")
                existing = self._threats.get(key)
                if (existing is None) or (threat.confidence >= existing.confidence):
                    updated = ThreatEntity(
                        label=threat.label,
                        category=threat.category,
                        confidence=threat.confidence,
                        severity=threat.severity,
                        location=threat.location,
                        provenance_engine=output.engine_id,
                    )
                    self._threats[key] = updated

            for action in output.actions:
                key = action.action.strip().lower()
                fields_written.append(f"actions.{key}")
                existing = self._actions.get(key)
                if (existing is None) or (action.confidence >= existing.confidence):
                    self._actions[key] = ActionCandidate(
                        action=action.action,
                        confidence=action.confidence,
                        priority=action.priority,
                        action_type=action.action_type,
                        rationale=action.rationale,
                    )

            for item in output.evidence:
                key = item.summary.strip().lower()[:140]
                fields_written.append(f"evidence.{key[:24]}")
                existing = self._evidence.get(key)
                if (existing is None) or (item.confidence >= existing.confidence):
                    self._evidence[key] = EvidenceItem(
                        summary=item.summary,
                        confidence=item.confidence,
                        source=item.source,
                        tags=list(item.tags),
                    )

            for update in output.state_updates:
                field_path = update.field_path
                fields_written.append(field_path)
                if field_path in self._field_values:
                    prior = self._field_values[field_path]
                    if prior != update.value:
                        prior_meta = self._field_provenance.get(field_path, {})
                        self._conflicts.append(
                            ConflictRecord(
                                conflict_id=str(uuid4()),
                                field_path=field_path,
                                existing_value=prior,
                                incoming_value=update.value,
                                existing_engine=str(prior_meta.get("engine_id", "unknown")),
                                incoming_engine=output.engine_id,
                                existing_confidence=float(prior_meta.get("confidence", 0.0)),
                                incoming_confidence=float(update.confidence),
                            )
                        )
                self._field_values[field_path] = update.value
                self._field_provenance[field_path] = {
                    "engine_id": output.engine_id,
                    "confidence": float(update.confidence),
                    "task_id": output.task_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            contribution.fields_written = fields_written
            self._contributions.append(contribution)
            self._bump_version(
                "engine_output_ingested",
                {
                    "engine_id": output.engine_id,
                    "task_id": output.task_id,
                    "fields_written": len(fields_written),
                },
            )
            return contribution

    def get_conflicts(self, *, pending_only: bool = False) -> List[ConflictRecord]:
        """Return conflict records, optionally only unresolved conflicts."""
        with self._lock:
            if pending_only:
                return [record for record in self._conflicts if not record.resolved]
            return list(self._conflicts)

    def resolve_conflict(
        self,
        conflict_id: str,
        *,
        strategy: str,
        resolved_value: Any,
        requires_human_review: bool = False,
    ) -> Optional[ConflictRecord]:
        """Mark one conflict as resolved and apply value to state."""
        with self._lock:
            for record in self._conflicts:
                if record.conflict_id != conflict_id:
                    continue
                record.resolved = True
                record.resolution_strategy = strategy
                record.resolved_value = resolved_value
                record.requires_human_review = requires_human_review
                self._field_values[record.field_path] = resolved_value
                self._field_provenance[record.field_path] = {
                    "engine_id": "reconciliation",
                    "confidence": max(record.existing_confidence, record.incoming_confidence),
                    "task_id": "reconciliation",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._bump_version(
                    "conflict_resolved",
                    {"conflict_id": conflict_id, "strategy": strategy},
                )
                return record
            return None

    def get_authoritative_threats(self) -> List[ThreatEntity]:
        """Return deduplicated threat entities ranked by confidence and trust."""
        with self._lock:
            ranked = sorted(
                self._threats.values(),
                key=lambda threat: (
                    threat.confidence * self.get_engine_trust(threat.provenance_engine or ""),
                    threat.severity == "high",
                ),
                reverse=True,
            )
            return list(ranked)

    def get_authoritative_actions(self) -> List[ActionCandidate]:
        """Return deduplicated action candidates ranked by confidence and priority."""
        with self._lock:
            ranked = sorted(
                self._actions.values(),
                key=lambda action: (action.confidence, -action.priority),
                reverse=True,
            )
            return list(ranked)

    def get_authoritative_evidence(self) -> List[EvidenceItem]:
        """Return deduplicated evidence ranked by confidence."""
        with self._lock:
            ranked = sorted(self._evidence.values(), key=lambda item: item.confidence, reverse=True)
            return list(ranked)

    def add_decision(self, decision: DecisionRecord) -> None:
        """Persist one authoritative decision record."""
        with self._lock:
            self._decisions.append(decision)
            self._bump_version("decision_recorded", {"decision_id": decision.decision_id})

    def get_decisions(self) -> List[DecisionRecord]:
        """Return all decision records."""
        with self._lock:
            return list(self._decisions)

    def snapshot(self) -> Dict[str, Any]:
        """Return full state snapshot for audit export."""
        with self._lock:
            return {
                "version": self._version,
                "context": self._context.to_dict(),
                "threats": [item.to_dict() for item in self.get_authoritative_threats()],
                "actions": [item.to_dict() for item in self.get_authoritative_actions()],
                "evidence": [item.to_dict() for item in self.get_authoritative_evidence()],
                "field_values": dict(self._field_values),
                "field_provenance": dict(self._field_provenance),
                "conflicts": [record.to_dict() for record in self._conflicts],
                "contributions": [item.to_dict() for item in self._contributions],
                "decisions": [item.to_dict() for item in self._decisions],
                "version_history": [item.to_dict() for item in self._versions],
                "engine_trust_weights": dict(self._engine_trust_weights),
                "domain_specialists": dict(self._domain_specialists),
            }

    def _bump_version(self, reason: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Increment state version and append immutable version record."""
        self._version += 1
        self._versions.append(
            StateVersion(
                version=self._version,
                reason=reason,
                metadata=dict(metadata or {}),
            )
        )
