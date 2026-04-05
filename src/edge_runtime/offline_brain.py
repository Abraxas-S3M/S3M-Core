"""Offline cognition helper for denied-connectivity mission continuity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class OfflineBrain:
    """
    Minimal offline planner state for MODE_D survival operations.

    The object tracks activation history and lightweight tactical intents so
    mission logic can continue without remote services.
    """

    active: bool = False
    activated_at: Optional[str] = None
    last_reason: Optional[str] = None
    intent_queue: List[str] = field(default_factory=list)

    def activate(self, reason: str) -> None:
        self.active = True
        self.activated_at = datetime.now(timezone.utc).isoformat()
        self.last_reason = str(reason)

    def enqueue_intent(self, intent: str) -> None:
        text = str(intent).strip()
        if not text:
            raise ValueError("intent must be non-empty")
        self.intent_queue.append(text)
        if len(self.intent_queue) > 256:
            self.intent_queue = self.intent_queue[-256:]

    def snapshot(self) -> Dict[str, object]:
        return {
            "active": self.active,
            "activated_at": self.activated_at,
            "last_reason": self.last_reason,
            "queued_intents": list(self.intent_queue),
        }
