"""Timeline Event Service — operational event log for CommandOverview.

The GUI expects timeline events categorized by type (decision, threat, comms,
logistics, intel) with timestamps and severity. This service collects events
from across the system and provides a queryable store.
"""

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

from pydantic import BaseModel


class TimelineEvent(BaseModel):
    id: str
    title: str
    category: str  # decision | threat | comms | logistics | intel
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    occurredAt: str
    details: str


class TimelineService:
    """In-memory timeline event store with category/time filtering."""

    _MAX_EVENTS = 2000

    def __init__(self) -> None:
        self._events: Deque[Dict] = deque(maxlen=self._MAX_EVENTS)

    def emit(
        self,
        title: str,
        category: str,
        severity: str = "MEDIUM",
        details: str = "",
    ) -> TimelineEvent:
        """Record a new operational event."""
        event = TimelineEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            title=title,
            category=category,
            severity=severity.upper(),
            occurredAt=datetime.now(timezone.utc).isoformat(),
            details=details,
        )
        self._events.appendleft(event.model_dump())
        return event

    def query(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Query events with optional category and severity filters."""
        results = []
        for evt in self._events:
            if category and evt.get("category") != category:
                continue
            if severity and evt.get("severity") != severity.upper():
                continue
            results.append(evt)
            if len(results) >= limit:
                break
        return results


# Global singleton
timeline_service = TimelineService()
