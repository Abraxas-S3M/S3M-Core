"""
S3M Episodic Memory — Time-Indexed Experience Store
===================================================
Stores discrete battlefield episodes (observation, action, outcome) and
retrieves them by tactical context, relevance, and recency.

Design constraints:
  - CPU-native, no embedding dependencies
  - Thread-safe under concurrent cognitive cycles
  - Bounded by entry capacity and memory-byte budget
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Episode(BaseModel):
    """One episodic memory record tied to a tactical event."""

    episode_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:16])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: str = ""
    tags: List[str] = Field(default_factory=list)
    observation: Dict[str, Any] = Field(default_factory=dict)
    action_taken: str = ""
    outcome: Dict[str, Any] = Field(default_factory=dict)
    reward: float = 0.0
    belief_state_id: Optional[str] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = 0
    created_epoch_s: float = Field(default_factory=time.time, exclude=True)


class EpisodicQuery(BaseModel):
    """Query parameters for episodic retrieval."""

    context: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    min_importance: float = 0.0
    max_age_seconds: Optional[float] = None
    limit: int = 10


class EpisodicMemory:
    """
    Bounded episodic memory with LRU+byte-budget eviction.

    Composite retrieval score:
      recency_weight * recency + relevance_weight * relevance + importance_weight * importance
    """

    def __init__(
        self,
        capacity: int = 10000,
        recency_weight: float = 0.4,
        relevance_weight: float = 0.35,
        importance_weight: float = 0.25,
        recency_halflife_seconds: float = 3600.0,
        max_memory_mb: float = 999.0,
    ) -> None:
        """Initialize bounded store parameters and ranking weights."""
        self._capacity = max(100, capacity)
        self._rw = recency_weight
        self._relw = relevance_weight
        self._iw = importance_weight
        self._halflife = max(1.0, recency_halflife_seconds)
        self._max_bytes = int(max(1.0, max_memory_mb) * 1024 * 1024)
        self._store: OrderedDict[str, Episode] = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._entry_bytes: Dict[str, int] = {}
        self._total_bytes = 0
        self._lock = threading.RLock()

    def store(self, episode: Episode) -> str:
        """Store one episode and evict oldest records if limits are exceeded."""
        with self._lock:
            episode_id = episode.episode_id
            now = time.time()
            episode.created_epoch_s = now

            if episode_id in self._store:
                self._total_bytes -= self._entry_bytes.get(episode_id, 0)

            self._store[episode_id] = episode
            self._timestamps[episode_id] = now
            estimated = self._estimate_episode_bytes(episode)
            self._entry_bytes[episode_id] = estimated
            self._total_bytes += estimated
            self._store.move_to_end(episode_id)
            self._evict_until_within_limits()
            return episode_id

    def query(
        self,
        context: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        min_importance: float = 0.0,
        max_age_seconds: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve episodes by composite score over recency, relevance, and importance."""
        with self._lock:
            now = time.time()
            query_tokens = set((context or "").lower().split())
            query_tags = set(tag.lower() for tag in (tags or []))
            candidates: List[tuple[str, Episode, float]] = []

            for episode_id, episode in self._store.items():
                if episode.importance < min_importance:
                    continue
                age_seconds = now - self._timestamps.get(episode_id, now)
                if max_age_seconds is not None and age_seconds > max_age_seconds:
                    continue

                recency = math.exp(-0.693 * age_seconds / self._halflife)
                episode_tokens = set(episode.context.lower().split()) | {
                    tag.lower() for tag in episode.tags
                }
                query_terms = query_tokens | query_tags
                if query_terms and episode_tokens:
                    intersection = len(query_terms & episode_tokens)
                    union = len(query_terms | episode_tokens)
                    relevance = intersection / union if union > 0 else 0.0
                elif not query_terms:
                    relevance = 0.5
                else:
                    relevance = 0.0

                score = self._rw * recency + self._relw * relevance + self._iw * episode.importance
                candidates.append((episode_id, episode, score))

            candidates.sort(key=lambda item: item[2], reverse=True)
            results: List[Dict[str, Any]] = []
            for episode_id, episode, score in candidates[: max(0, limit)]:
                episode.access_count += 1
                self._store.move_to_end(episode_id)
                results.append(
                    {
                        "episode_id": episode_id,
                        "episode": episode.model_dump(),
                        "score": score,
                    }
                )
            return results

    def size(self) -> int:
        """Return number of episodes currently retained."""
        with self._lock:
            return len(self._store)

    def current_memory_bytes(self) -> int:
        """Return approximate memory consumed by episodic records."""
        with self._lock:
            return self._total_bytes

    def clear(self) -> None:
        """Remove all episodes and reset byte accounting."""
        with self._lock:
            self._store.clear()
            self._timestamps.clear()
            self._entry_bytes.clear()
            self._total_bytes = 0

    def _evict_until_within_limits(self) -> None:
        while self._store and (
            len(self._store) > self._capacity or self._total_bytes > self._max_bytes
        ):
            oldest_id = next(iter(self._store))
            del self._store[oldest_id]
            self._timestamps.pop(oldest_id, None)
            self._total_bytes -= self._entry_bytes.pop(oldest_id, 0)

    @staticmethod
    def _estimate_episode_bytes(episode: Episode) -> int:
        try:
            return len(episode.model_dump_json().encode("utf-8"))
        except Exception:
            return 512
