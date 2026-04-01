"""Tracing bridge hooks for Langfuse/Phoenix integration in S3M."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional


@dataclass
class TraceSpan:
    trace_id: str
    name: str
    started_at: datetime
    metadata: Dict[str, str]


class TracingBridge:
    """Minimal tracing abstraction that can be wired to existing tracing stacks."""

    def __init__(self) -> None:
        self._active_spans: Dict[str, TraceSpan] = {}

    def start_span(self, trace_id: str, name: str, metadata: Optional[Dict[str, str]] = None) -> TraceSpan:
        span = TraceSpan(
            trace_id=trace_id,
            name=name,
            started_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self._active_spans[trace_id] = span
        return span

    def end_span(self, trace_id: str) -> Optional[TraceSpan]:
        return self._active_spans.pop(trace_id, None)

    @contextmanager
    def span(self, trace_id: str, name: str, metadata: Optional[Dict[str, str]] = None) -> Iterator[TraceSpan]:
        span = self.start_span(trace_id=trace_id, name=name, metadata=metadata)
        try:
            yield span
        finally:
            self.end_span(trace_id)
