"""Dynamic tactical priority management for real-time arbitration.

This module tracks evolving command priorities so survival and ROE concerns can
preempt lower-value mission behavior during fast-changing engagements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import time
from typing import Dict, List, Optional


CATEGORY_WEIGHTS: Dict[str, float] = {
    "survival": 1.5,
    "commander": 1.4,
    "roe": 1.3,
    "mission": 1.0,
    "resource": 0.95,
    "intel": 0.85,
    "formation": 0.8,
}


@dataclass
class TacticalPriority:
    """One time-evolving tactical priority entry."""

    priority_id: str
    category: str
    base_priority: float
    escalation_rate: float = 0.0
    decay_rate: float = 0.0
    ttl_seconds: float = 30.0
    created_at: float = field(default_factory=time.monotonic)

    def effective_priority(self, now: Optional[float] = None) -> float:
        t = float(now if now is not None else time.monotonic())
        dt = max(0.0, t - self.created_at)
        weight = CATEGORY_WEIGHTS.get(self.category, 1.0)
        raw = self.base_priority + (self.escalation_rate * dt) - (self.decay_rate * dt)
        return max(0.0, raw * weight)

    def is_expired(self, now: Optional[float] = None) -> bool:
        t = float(now if now is not None else time.monotonic())
        return (t - self.created_at) > max(0.1, self.ttl_seconds)


class PriorityManager:
    """Maintains dynamic priority heap with interrupt detection."""

    def __init__(self, interrupt_threshold: float = 0.25) -> None:
        self.interrupt_threshold = max(0.0, float(interrupt_threshold))
        self._entries: Dict[str, TacticalPriority] = {}
        self._now = 0.0
        self._real_clock = time.monotonic()

    def add_priority(
        self,
        priority: TacticalPriority | str,
        base_priority: float | None = None,
        category: str | None = None,
        escalation_rate: float = 0.0,
        decay_rate: float = 0.0,
        ttl_seconds: float = 30.0,
    ) -> None:
        """Add a priority entry from object or parameter tuple."""
        if isinstance(priority, TacticalPriority):
            item = priority
            if item.created_at is None:  # pragma: no cover - defensive
                item.created_at = self._now
        else:
            if base_priority is None or category is None:
                raise ValueError("base_priority and category are required when adding by id")
            item = TacticalPriority(
                priority_id=str(priority),
                category=str(category),
                base_priority=float(base_priority),
                escalation_rate=float(escalation_rate),
                decay_rate=float(decay_rate),
                ttl_seconds=float(ttl_seconds),
                created_at=self._now,
            )
        self._entries[item.priority_id] = item

    def remove_priority(self, priority_id: str) -> None:
        self._entries.pop(priority_id, None)

    def tick(self, dt: Optional[float] = None) -> List[Dict[str, float]]:
        """Garbage-collect expired priorities and return ranked active list."""
        if dt is None:
            current = time.monotonic()
            dt = max(0.0, current - self._real_clock)
            self._real_clock = current
        self._now += max(0.0, float(dt))
        now = self._now
        expired = [pid for pid, p in self._entries.items() if p.is_expired(now) or p.effective_priority(now) < 1e-4]
        for pid in expired:
            self._entries.pop(pid, None)
        return self.active_priorities()

    def active_priorities(self) -> List[Dict[str, float]]:
        now = self._now
        heap: List[tuple[float, str, TacticalPriority]] = []
        for pid, p in self._entries.items():
            heapq.heappush(heap, (-p.effective_priority(now), pid, p))
        ranked: List[Dict[str, float]] = []
        while heap:
            neg, pid, p = heapq.heappop(heap)
            ranked.append(
                {
                    "priority_id": pid,
                    "category": p.category,
                    "effective_priority": -neg,
                }
            )
        return ranked

    def top_priority(self) -> Optional[Dict[str, float]]:
        ranked = self.active_priorities()
        return ranked[0] if ranked else None

    def top(self) -> Optional[TacticalPriority]:
        """Return top priority object (arbiter compatibility helper)."""
        now = self._now
        if not self._entries:
            return None
        return max(self._entries.values(), key=lambda p: p.effective_priority(now))

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        now = self._now
        return {
            pid: {
                "effective_priority": p.effective_priority(now),
                "base_priority": p.base_priority,
                "category": p.category,
            }
            for pid, p in self._entries.items()
        }

    def should_interrupt(self, current_priority: Optional[float] = None, incoming_priority: Optional[float] = None) -> bool:
        if current_priority is not None and incoming_priority is not None:
            return float(incoming_priority) >= float(current_priority) + self.interrupt_threshold
        ranked = self.active_priorities()
        if len(ranked) < 2:
            return False
        return float(ranked[0]["effective_priority"]) >= float(ranked[1]["effective_priority"]) + self.interrupt_threshold

