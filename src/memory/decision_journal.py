"""
S3M Decision Journal — Persistent Decision Audit Log with Replay
=================================================================
Records cognitive decisions with bilingual rationale and replayable context for:
  - Post-action tactical review
  - Accountability and legal audit trails
  - Counterfactual learning
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JournalEntry(BaseModel):
    """One immutable-style decision journal entry."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decision_id: str = ""
    mission_id: Optional[str] = None
    selected_action: str = ""
    confidence: float = 0.0
    utility_score: float = 0.0
    belief_snapshot: Dict[str, float] = Field(default_factory=dict)
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    rationale_en: str = ""
    rationale_ar: str = ""
    outcome: Optional[Dict[str, Any]] = None
    outcome_reward: Optional[float] = None
    requires_human_review: bool = False
    human_override: Optional[str] = None
    context_tags: List[str] = Field(default_factory=list)


class JournalQuery(BaseModel):
    """Query filters for journal retrieval."""

    mission_id: Optional[str] = None
    action_filter: Optional[str] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None
    has_outcome: Optional[bool] = None
    limit: int = 50


class DecisionJournal:
    """Thread-safe decision journal with optional JSONL persistence."""

    def __init__(
        self,
        capacity: int = 50000,
        persist_path: Optional[str] = None,
        max_memory_mb: float = 999.0,
    ) -> None:
        """Initialize bounded in-memory journal and optional disk-backed replay log."""
        self._entries: List[JournalEntry] = []
        self._entry_bytes: List[int] = []
        self._index_by_decision: Dict[str, int] = {}
        self._index_by_mission: Dict[str, List[int]] = defaultdict(list)
        self._capacity = max(1000, capacity)
        self._max_bytes = int(max(1.0, max_memory_mb) * 1024 * 1024)
        self._total_bytes = 0
        self._persist_path = Path(persist_path) if persist_path else None
        self._lock = threading.RLock()

        if self._persist_path and self._persist_path.exists():
            self._load_from_disk()

    def record(self, entry: JournalEntry) -> str:
        """Append a decision entry and enforce capacity/memory constraints."""
        with self._lock:
            index = len(self._entries)
            self._entries.append(entry)
            size_bytes = self._estimate_entry_bytes(entry)
            self._entry_bytes.append(size_bytes)
            self._total_bytes += size_bytes
            self._index_by_decision[entry.decision_id] = index
            if entry.mission_id:
                self._index_by_mission[entry.mission_id].append(index)

            self._evict_until_within_limits()

            if self._persist_path:
                self._append_to_disk(entry)
            return entry.entry_id

    def attach_outcome(self, decision_id: str, outcome: Dict[str, Any], reward: float = 0.0) -> bool:
        """Attach observed outcome to a prior decision entry by decision_id."""
        with self._lock:
            index = self._index_by_decision.get(decision_id)
            if index is None or index >= len(self._entries):
                return False
            old_entry = self._entries[index]
            old_size = self._entry_bytes[index]
            new_entry = old_entry.model_copy(update={"outcome": outcome, "outcome_reward": reward})
            self._entries[index] = new_entry
            new_size = self._estimate_entry_bytes(new_entry)
            self._entry_bytes[index] = new_size
            self._total_bytes += new_size - old_size
            self._evict_until_within_limits()
            return True

    def query(
        self,
        mission_id: Optional[str] = None,
        action_filter: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_confidence: Optional[float] = None,
        has_outcome: Optional[bool] = None,
        limit: int = 50,
    ) -> List[JournalEntry]:
        """Query journal entries with filter predicates and reverse-chronological order."""
        with self._lock:
            if mission_id and mission_id in self._index_by_mission:
                candidate_indices = self._index_by_mission[mission_id]
                candidates = [self._entries[i] for i in candidate_indices if i < len(self._entries)]
            else:
                candidates = list(self._entries)

            results: List[JournalEntry] = []
            for entry in reversed(candidates):
                if action_filter and entry.selected_action != action_filter:
                    continue
                if min_confidence is not None and entry.confidence < min_confidence:
                    continue
                if max_confidence is not None and entry.confidence > max_confidence:
                    continue
                if has_outcome is True and entry.outcome is None:
                    continue
                if has_outcome is False and entry.outcome is not None:
                    continue
                results.append(entry)
                if len(results) >= max(0, limit):
                    break
            return results

    def analyze_patterns(self, last_n: int = 100) -> Dict[str, Any]:
        """Compute aggregate action/confidence/review statistics over recent entries."""
        with self._lock:
            recent = self._entries[-max(0, last_n) :]
            if not recent:
                return {"total": 0}

            action_counts: Dict[str, int] = defaultdict(int)
            confidence_sum = 0.0
            reward_sum = 0.0
            reward_count = 0
            human_review_count = 0

            for entry in recent:
                action_counts[entry.selected_action] += 1
                confidence_sum += entry.confidence
                if entry.outcome_reward is not None:
                    reward_sum += entry.outcome_reward
                    reward_count += 1
                if entry.requires_human_review:
                    human_review_count += 1

            return {
                "total": len(recent),
                "action_distribution": dict(action_counts),
                "avg_confidence": confidence_sum / len(recent),
                "avg_reward": reward_sum / reward_count if reward_count > 0 else None,
                "human_review_rate": human_review_count / len(recent),
                "most_common_action": max(action_counts, key=action_counts.get) if action_counts else None,
            }

    def size(self) -> int:
        """Return number of retained journal entries."""
        with self._lock:
            return len(self._entries)

    def current_memory_bytes(self) -> int:
        """Return approximate bytes retained in memory for entries."""
        with self._lock:
            return self._total_bytes

    def _evict_until_within_limits(self) -> None:
        while self._entries and (
            len(self._entries) > self._capacity or self._total_bytes > self._max_bytes
        ):
            removed_size = self._entry_bytes.pop(0)
            self._entries.pop(0)
            self._total_bytes -= removed_size
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        self._index_by_decision.clear()
        self._index_by_mission.clear()
        for index, entry in enumerate(self._entries):
            self._index_by_decision[entry.decision_id] = index
            if entry.mission_id:
                self._index_by_mission[entry.mission_id].append(index)

    def _append_to_disk(self, entry: JournalEntry) -> None:
        try:
            if self._persist_path is None:
                return
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")
        except Exception:
            # Tactical continuity favors in-memory operation if disk persistence fails.
            pass

    def _load_from_disk(self) -> None:
        try:
            if self._persist_path is None:
                return
            with self._persist_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    record = line.strip()
                    if not record:
                        continue
                    entry = JournalEntry.model_validate_json(record)
                    self._entries.append(entry)
                    size_bytes = self._estimate_entry_bytes(entry)
                    self._entry_bytes.append(size_bytes)
                    self._total_bytes += size_bytes
            self._evict_until_within_limits()
        except Exception:
            pass

    @staticmethod
    def _estimate_entry_bytes(entry: JournalEntry) -> int:
        try:
            return len(entry.model_dump_json().encode("utf-8"))
        except Exception:
            return 512
