"""AI-ready internal event bus for the S3M-Core COP layer.

Tactical context:
    This is the seam between the deterministic C4ISR/COP demonstration layer and
    the *future* S3M quad-engine AI reasoning orchestrator. Every meaningful COP
    activity (track update, alert, decision request, operator note, sensor
    report) is published here as a normalized ``CopEvent`` carrying an
    ``ai_context`` routing hint.

    IMPORTANT: This bus does NOT call any live LLM, Grok/xAI endpoint, RunPod
    job, trainer, or sync daemon. It is an in-memory, bounded buffer that the
    future orchestrator can subscribe to. Building this seam now keeps a clean,
    auditable bridge without enabling any autonomous reasoning yet.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

# Recognized event types flowing toward the future AI orchestrator.
EVENT_TYPES: tuple[str, ...] = (
    "track_update",
    "alert",
    "decision_request",
    "operator_note",
    "sensor_report",
    # Mission lifecycle + Cortex quarantine advisories (trusted structured payloads).
    "mission_activate",
    "mission_end",
    "cortex_recommendation",
)

# Routing hints the future quad-engine orchestrator can use to select a reasoning
# path. No engine is invoked here; these are advisory labels only.
ROUTE_HINTS: tuple[str, ...] = (
    "tactical",
    "reasoning",
    "planning",
    "arabic_nlp",
)


class AIContext(BaseModel):
    """Advisory routing context for the future quad-engine orchestrator."""

    route_hint: str = "tactical"
    confidence: float = 0.0
    requires_human_review: bool = True


class CopEvent(BaseModel):
    """Normalized COP event published toward the future AI reasoning layer."""

    event_id: str
    track: str
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    ai_context: AIContext = Field(default_factory=AIContext)
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    *,
    track: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    route_hint: str = "tactical",
    confidence: float = 0.0,
    requires_human_review: bool = True,
    event_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> CopEvent:
    """Construct a :class:`CopEvent`.

    ``event_id`` may be supplied for deterministic demo streams; otherwise a
    deterministic id derived from the track, type, and timestamp is used so the
    bus never depends on randomness.
    """
    safe_type = event_type if event_type in EVENT_TYPES else "track_update"
    safe_hint = route_hint if route_hint in ROUTE_HINTS else "tactical"
    stamp = created_at or _now_iso()
    resolved_id = event_id or f"evt-{track}-{safe_type}-{stamp}"
    return CopEvent(
        event_id=resolved_id,
        track=str(track),
        event_type=safe_type,
        payload=dict(payload or {}),
        ai_context=AIContext(
            route_hint=safe_hint,
            confidence=float(confidence),
            requires_human_review=bool(requires_human_review),
        ),
        created_at=stamp,
    )


class CopEventBus:
    """Thread-safe, bounded, in-memory COP event buffer.

    The buffer is intentionally simple: it retains the most recent events per
    track for inspection by the future orchestrator and by audit tooling. It
    performs no outbound network calls.
    """

    def __init__(self, *, max_events_per_track: int = 200) -> None:
        self._max_events_per_track = max(1, int(max_events_per_track))
        self._buffers: Dict[str, Deque[CopEvent]] = {}
        self._subscribers: List[Callable[[CopEvent], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Callable[[CopEvent], None]) -> None:
        """Register an in-process subscriber (e.g. Cortex mission awareness)."""
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, event: CopEvent) -> CopEvent:
        subscribers: List[Callable[[CopEvent], None]]
        with self._lock:
            buffer = self._buffers.get(event.track)
            if buffer is None:
                buffer = deque(maxlen=self._max_events_per_track)
                self._buffers[event.track] = buffer
            buffer.append(event)
            subscribers = list(self._subscribers)
        for handler in subscribers:
            handler(event)
        return event

    def emit(
        self,
        *,
        track: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        route_hint: str = "tactical",
        confidence: float = 0.0,
        requires_human_review: bool = True,
        event_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> CopEvent:
        """Build and publish an event in one step."""
        event = build_event(
            track=track,
            event_type=event_type,
            payload=payload,
            route_hint=route_hint,
            confidence=confidence,
            requires_human_review=requires_human_review,
            event_id=event_id,
            created_at=created_at,
        )
        return self.publish(event)

    def recent(self, track: Optional[str] = None, *, limit: int = 50) -> List[CopEvent]:
        bounded = max(1, int(limit))
        with self._lock:
            if track is not None:
                buffer = self._buffers.get(str(track))
                if not buffer:
                    return []
                return list(buffer)[-bounded:]
            merged: List[CopEvent] = []
            for buffer in self._buffers.values():
                merged.extend(buffer)
        merged.sort(key=lambda evt: evt.created_at)
        return merged[-bounded:]

    def clear(self, track: Optional[str] = None) -> None:
        with self._lock:
            if track is None:
                self._buffers.clear()
            else:
                self._buffers.pop(str(track), None)


_GLOBAL_BUS: Optional[CopEventBus] = None
_GLOBAL_BUS_LOCK = threading.Lock()


def get_event_bus() -> CopEventBus:
    """Return the process-wide COP event bus singleton."""
    global _GLOBAL_BUS
    if _GLOBAL_BUS is None:
        with _GLOBAL_BUS_LOCK:
            if _GLOBAL_BUS is None:
                _GLOBAL_BUS = CopEventBus()
    return _GLOBAL_BUS
