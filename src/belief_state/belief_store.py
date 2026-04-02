"""Belief-state storage, merge, and auditing runtime for S3M."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import logging
import math
import threading
from typing import Callable, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .models import (
    BeliefHypothesis,
    BeliefState,
    BeliefUpdate,
    DoctrineContext,
    EntityRef,
    EvidenceLink,
    HypothesisStatus,
    UncertaintyMetrics,
)


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AuditEntry(BaseModel):
    """Immutable audit record for one committed belief-state transition."""

    model_config = ConfigDict(frozen=True)

    entry_id: UUID = Field(default_factory=uuid4)
    from_version: Optional[int] = None
    to_version: int
    timestamp: datetime = Field(default_factory=_utc_now)
    author: str
    update_ids: List[str] = Field(default_factory=list)
    change_summary: str
    hypothesis_delta: Dict[str, str] = Field(default_factory=dict)
    entity_delta: Dict[str, str] = Field(default_factory=dict)
    snapshot_id: str


class MergeConflict(BaseModel):
    """Immutable record describing a merge-time delta conflict."""

    model_config = ConfigDict(frozen=True)

    conflict_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=_utc_now)
    hypothesis_id: str
    update_a_id: str
    update_b_id: str
    delta_a: float
    delta_b: float
    resolution: str
    resolved_delta: float


class _Builder:
    """Mutable assembler used to produce immutable belief-state snapshots."""

    def __init__(self, state: BeliefState) -> None:
        self.entities: Dict[str, EntityRef] = copy.deepcopy(state.entities)
        self.hypotheses: Dict[str, BeliefHypothesis] = copy.deepcopy(state.hypotheses)
        self.confidence_distribution: Dict[str, float] = copy.deepcopy(
            state.confidence_distribution
        )
        self.evidence_links: Dict[str, EvidenceLink] = copy.deepcopy(state.evidence_links)
        self.doctrine_context: DoctrineContext = copy.deepcopy(state.doctrine_context)
        self.applied: List[str] = copy.deepcopy(state.applied_updates)
        self.uncertainty_metrics: UncertaintyMetrics = copy.deepcopy(
            state.uncertainty_metrics
        )

    def upsert_entity(self, entity: EntityRef) -> None:
        """Insert or replace an entity reference by ID."""
        self.entities[str(entity.entity_id)] = copy.deepcopy(entity)

    def add_hypothesis(self, hypothesis: BeliefHypothesis) -> None:
        """Insert or replace a hypothesis and seed active confidence."""
        hypothesis_id = str(hypothesis.hypothesis_id)
        stored = copy.deepcopy(hypothesis)
        self.hypotheses[hypothesis_id] = stored
        if stored.status == HypothesisStatus.ACTIVE:
            self.confidence_distribution[hypothesis_id] = stored.probability
        else:
            self.confidence_distribution.pop(hypothesis_id, None)

    def retire_hypothesis(self, hypothesis_id: str) -> None:
        """Refute a hypothesis and remove it from active distribution."""
        if hypothesis_id not in self.hypotheses:
            return
        current = self.hypotheses[hypothesis_id]
        self.hypotheses[hypothesis_id] = current.model_copy(
            update={
                "status": HypothesisStatus.REFUTED,
                "probability": 0.0,
                "updated_at": _utc_now(),
            }
        )
        self.confidence_distribution.pop(hypothesis_id, None)

    def apply_delta(self, hypothesis_id: str, delta: float) -> None:
        """Apply and clamp probability delta for an existing hypothesis."""
        if hypothesis_id not in self.hypotheses:
            return
        current = self.hypotheses[hypothesis_id]
        new_probability = max(0.0, min(1.0, current.probability + delta))
        updated = current.model_copy(
            update={"probability": new_probability, "updated_at": _utc_now()}
        )
        self.hypotheses[hypothesis_id] = updated
        if updated.status == HypothesisStatus.ACTIVE:
            self.confidence_distribution[hypothesis_id] = new_probability
        else:
            self.confidence_distribution.pop(hypothesis_id, None)

    def attach_evidence(self, hypothesis_id: str, evidence: EvidenceLink) -> None:
        """Attach evidence globally and to the supporting list of a hypothesis."""
        self.evidence_links[str(evidence.evidence_id)] = copy.deepcopy(evidence)
        if hypothesis_id not in self.hypotheses:
            return
        current = self.hypotheses[hypothesis_id]
        supporting = list(current.supporting_evidence)
        supporting.append(copy.deepcopy(evidence))
        self.hypotheses[hypothesis_id] = current.model_copy(
            update={"supporting_evidence": supporting, "updated_at": _utc_now()}
        )

    def normalise(self) -> None:
        """Normalise active hypothesis probabilities into a valid distribution."""
        active_ids = [
            hypothesis_id
            for hypothesis_id, hypothesis in self.hypotheses.items()
            if hypothesis.status == HypothesisStatus.ACTIVE
        ]
        active_set = set(active_ids)

        for hypothesis_id in list(self.confidence_distribution.keys()):
            if hypothesis_id not in active_set:
                self.confidence_distribution.pop(hypothesis_id, None)

        if not active_ids:
            self.confidence_distribution = {}
            return

        for hypothesis_id in active_ids:
            if hypothesis_id not in self.confidence_distribution:
                probability = self.hypotheses[hypothesis_id].probability
                self.confidence_distribution[hypothesis_id] = max(0.0, min(1.0, probability))

        total = sum(self.confidence_distribution[hypothesis_id] for hypothesis_id in active_ids)
        if total == 0.0:
            logger.warning(
                "Collapsed active distribution; restoring uniform tactical prior."
            )
            uniform = 1.0 / float(len(active_ids))
            for hypothesis_id in active_ids:
                self.confidence_distribution[hypothesis_id] = uniform
        else:
            for hypothesis_id in active_ids:
                self.confidence_distribution[hypothesis_id] = (
                    self.confidence_distribution[hypothesis_id] / total
                )

        for hypothesis_id in active_ids:
            current = self.hypotheses[hypothesis_id]
            self.hypotheses[hypothesis_id] = current.model_copy(
                update={"probability": self.confidence_distribution[hypothesis_id]}
            )

    def build(
        self, new_version: int, applied_ids: List[str], parent_version: Optional[int]
    ) -> BeliefState:
        """Build an immutable belief-state snapshot with computed uncertainty."""
        distribution = copy.deepcopy(self.confidence_distribution)
        leading_probability = max(distribution.values()) if distribution else 0.0
        entropy = -sum(
            probability * math.log(probability)
            for probability in distribution.values()
            if probability > 0.0
        )
        uncertainty_metrics = UncertaintyMetrics(
            epistemic_uncertainty=1.0 - leading_probability,
            aleatoric_uncertainty=self.uncertainty_metrics.aleatoric_uncertainty,
            entropy=entropy,
            confidence_interval=(
                max(0.0, leading_probability - 0.05),
                min(1.0, leading_probability + 0.05),
            ),
            staleness_seconds=0.0,
        )

        return BeliefState(
            version=new_version,
            parent_version=parent_version,
            entities=copy.deepcopy(self.entities),
            hypotheses=copy.deepcopy(self.hypotheses),
            confidence_distribution=distribution,
            uncertainty_metrics=uncertainty_metrics,
            evidence_links=copy.deepcopy(self.evidence_links),
            doctrine_context=copy.deepcopy(self.doctrine_context),
            applied_updates=list(applied_ids),
        )


class BeliefStore:
    """Thread-safe runtime store for immutable belief-state snapshots."""

    RESOLVE_AVERAGE = "AVERAGE"
    RESOLVE_MAX = "MAX"

    def __init__(self, max_history: int = 200, conflict_threshold: float = 0.15):
        """Initialise a store with genesis snapshot and empty logs."""
        if max_history < 1:
            raise ValueError("max_history must be >= 1")
        self._max_history = max_history
        self._conflict_threshold = conflict_threshold
        self._lock = threading.RLock()
        self._snapshots: List[BeliefState] = [BeliefState(version=0)]
        self._audit: List[AuditEntry] = []
        self._conflicts: List[MergeConflict] = []
        self._subscribers: List[Callable[[BeliefState], None]] = []

    def current(self) -> BeliefState:
        """Return the current immutable belief-state snapshot."""
        return self._snapshots[-1]

    def history(self, n: int = 20) -> List[BeliefState]:
        """Return up to n snapshots ordered from oldest to newest."""
        if n <= 0:
            return []
        return list(self._snapshots[-n:])

    def audit_log(self, n: int = 50) -> List[AuditEntry]:
        """Return up to n audit entries ordered from oldest to newest."""
        if n <= 0:
            return []
        return list(self._audit[-n:])

    def conflicts(self) -> List[MergeConflict]:
        """Return all recorded merge conflict records."""
        return list(self._conflicts)

    def get_version(self, version: int) -> Optional[BeliefState]:
        """Return a snapshot for version if present in retained history."""
        for snapshot in self._snapshots:
            if snapshot.version == version:
                return snapshot
        return None

    def create(
        self,
        hypotheses: List[BeliefHypothesis],
        entities: Optional[List[EntityRef]] = None,
        doctrine: Optional[DoctrineContext] = None,
        evidence: Optional[Dict[str, List[EvidenceLink]]] = None,
        author: str = "system",
    ) -> BeliefState:
        """Create a new snapshot by adding provided seed content."""
        if not hypotheses:
            raise ValueError("hypotheses must not be empty")

        with self._lock:
            previous = self.current()
            builder = _Builder(previous)

            for hypothesis in hypotheses:
                builder.add_hypothesis(hypothesis)
            for entity in entities or []:
                builder.upsert_entity(entity)
            if doctrine is not None:
                builder.doctrine_context = copy.deepcopy(doctrine)
            for hypothesis_id, links in (evidence or {}).items():
                for link in links:
                    builder.attach_evidence(hypothesis_id, link)

            builder.normalise()
            new_state = builder.build(
                new_version=previous.version + 1,
                applied_ids=builder.applied,
                parent_version=previous.version,
            )
            entry = self._make_audit_entry(
                previous, new_state, [], author, summary="create"
            )
            self._commit(new_state, entry)

        self._notify(new_state)
        return new_state

    def apply(self, update: BeliefUpdate, author: str = "system") -> BeliefState:
        """Apply one belief update and commit a new snapshot."""
        with self._lock:
            previous = self.current()
            builder = _Builder(previous)
            self._apply_single_update(builder, update)
            builder.normalise()
            new_state = builder.build(
                new_version=previous.version + 1,
                applied_ids=builder.applied,
                parent_version=previous.version,
            )
            entry = self._make_audit_entry(
                previous, new_state, [update], author, summary="apply"
            )
            self._commit(new_state, entry)

        self._notify(new_state)
        return new_state

    def merge(
        self,
        updates: List[BeliefUpdate],
        author: str = "system",
        strategy: str = RESOLVE_AVERAGE,
    ) -> BeliefState:
        """Merge multiple updates with conflict resolution and commit."""
        if not updates:
            raise ValueError("updates must not be empty")

        with self._lock:
            previous = self.current()
            builder = _Builder(previous)

            merged_deltas = self._resolve_conflicts(updates, strategy)
            for update in updates:
                self._apply_single_update(builder, update, skip_delta=True)
            for hypothesis_id, delta in merged_deltas.items():
                builder.apply_delta(hypothesis_id, delta)

            builder.normalise()
            new_state = builder.build(
                new_version=previous.version + 1,
                applied_ids=builder.applied,
                parent_version=previous.version,
            )
            entry = self._make_audit_entry(
                previous,
                new_state,
                updates,
                author,
                summary=f"merge:{len(updates)}",
            )
            self._commit(new_state, entry)

        self._notify(new_state)
        return new_state

    def export_json(self, version: Optional[int] = None) -> str:
        """Export one snapshot as JSON, defaulting to current version."""
        state = self.current() if version is None else self.get_version(version)
        if state is None:
            raise KeyError(f"belief state version {version} not found")
        return state.model_dump_json()

    def export_audit_json(self, n: int = 50) -> str:
        """Export the last n audit entries as a JSON array."""
        entries = self.audit_log(n=n)
        return TypeAdapter(List[AuditEntry]).dump_json(entries).decode("utf-8")

    def subscribe(self, callback: Callable[[BeliefState], None]) -> None:
        """Register a callback invoked after each successful commit."""
        self._subscribers.append(callback)

    def _resolve_conflicts(
        self, updates: List[BeliefUpdate], strategy: str
    ) -> Dict[str, float]:
        grouped: Dict[str, List[tuple[str, float]]] = {}
        for update in updates:
            update_id = str(update.update_id)
            for hypothesis_id, delta in update.delta.items():
                grouped.setdefault(hypothesis_id, []).append((update_id, delta))

        merged: Dict[str, float] = {}
        for hypothesis_id, records in grouped.items():
            deltas = [delta for _, delta in records]
            spread = abs(max(deltas) - min(deltas))

            if spread > self._conflict_threshold:
                if strategy == self.RESOLVE_MAX:
                    resolved = max(deltas, key=lambda value: abs(value))
                else:
                    resolved = sum(deltas) / float(len(deltas))

                min_idx = deltas.index(min(deltas))
                max_idx = deltas.index(max(deltas))
                conflict = MergeConflict(
                    hypothesis_id=hypothesis_id,
                    update_a_id=records[min_idx][0],
                    update_b_id=records[max_idx][0],
                    delta_a=deltas[min_idx],
                    delta_b=deltas[max_idx],
                    resolution=strategy,
                    resolved_delta=resolved,
                )
                self._conflicts.append(conflict)
                merged[hypothesis_id] = resolved
            else:
                merged[hypothesis_id] = sum(deltas)
        return merged

    def _apply_single_update(
        self, builder: _Builder, update: BeliefUpdate, skip_delta: bool = False
    ) -> None:
        for hypothesis in update.new_hypotheses:
            builder.add_hypothesis(hypothesis)
        for hypothesis_id in update.retired_ids:
            builder.retire_hypothesis(hypothesis_id)
        for entity in update.entity_updates:
            builder.upsert_entity(entity)
        for hypothesis_id, links in update.new_evidence.items():
            for link in links:
                builder.attach_evidence(hypothesis_id, link)
        if update.doctrine_update is not None:
            builder.doctrine_context = copy.deepcopy(update.doctrine_update)
        if not skip_delta:
            for hypothesis_id, delta in update.delta.items():
                builder.apply_delta(hypothesis_id, delta)
        builder.applied.append(str(update.update_id))

    def _make_audit_entry(
        self,
        previous: BeliefState,
        new: BeliefState,
        updates: List[BeliefUpdate],
        author: str,
        summary: str,
    ) -> AuditEntry:
        diff = previous.diff(new)

        hypothesis_delta: Dict[str, str] = {}
        for hypothesis_id in diff["hypotheses_added"]:
            hypothesis_delta[hypothesis_id] = "ADDED"
        for hypothesis_id in diff["hypotheses_removed"]:
            hypothesis_delta[hypothesis_id] = "REMOVED"
        for hypothesis_id in diff["hypotheses_changed"]:
            hypothesis_delta[hypothesis_id] = "CHANGED"

        entity_delta: Dict[str, str] = {}
        for entity_id in diff["entities_added"]:
            entity_delta[entity_id] = "ADDED"
        for entity_id in diff["entities_removed"]:
            entity_delta[entity_id] = "REMOVED"
        for entity_id in diff["entities_changed"]:
            entity_delta[entity_id] = "CHANGED"

        return AuditEntry(
            from_version=previous.version,
            to_version=new.version,
            author=author,
            update_ids=[str(update.update_id) for update in updates],
            change_summary=summary,
            hypothesis_delta=hypothesis_delta,
            entity_delta=entity_delta,
            snapshot_id=str(new.state_id),
        )

    def _commit(self, state: BeliefState, entry: AuditEntry) -> None:
        self._snapshots.append(state)
        self._audit.append(entry)
        while len(self._snapshots) > self._max_history:
            self._snapshots.pop(0)
        max_audit = max(0, self._max_history - 1)
        while len(self._audit) > max_audit:
            self._audit.pop(0)

    def _notify(self, state: BeliefState) -> None:
        for callback in list(self._subscribers):
            try:
                callback(state)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.warning("BeliefStore subscriber callback failed: %s", exc)
