"""OpenTelemetry tracing for the Cortex decision pipeline (local export only).

Military/tactical context: contested cyber ops need a span chain tied to one case ID
so auditors can replay council → planner → gate → broker → verification offline.
The trace ID is forced to match the case ID (128-bit OTEL trace id).
"""

from __future__ import annotations

import json
import hashlib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterator, Optional

from src.cortex.scrubber import scrub_mapping, scrub_text

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.trace import NonRecordingSpan, SpanKind, TraceFlags, set_span_in_context
    from opentelemetry.trace.span import SpanContext

    _HAS_OTEL = True
except ImportError:  # pragma: no cover - exercised when otel optional dep missing
    trace = None  # type: ignore[assignment]
    _HAS_OTEL = False


def case_id_to_trace_id(case_id: str) -> int:
    """Map a case UUID (or arbitrary id) to a 128-bit OpenTelemetry trace id."""
    cleaned = str(case_id).replace("-", "").strip().lower()
    if len(cleaned) == 32:
        try:
            return int(cleaned, 16)
        except ValueError:
            pass
    digest = hashlib.sha256(str(case_id).encode("utf-8")).hexdigest()
    return int(digest[:32], 16)


@dataclass(frozen=True, slots=True)
class LocalTraceExport:
    """JSONL trace bundle written beside the case workspace."""

    path: Path
    case_id: str
    trace_id_hex: str

    def read_text(self) -> str:
        if not self.path.is_file():
            return ""
        return self.path.read_text(encoding="utf-8")


if _HAS_OTEL:

    class _ScrubbingFileSpanExporter(SpanExporter):
        """Writes span snapshots to JSONL without external collectors."""

        def __init__(self, output_path: Path, *, case_id: str, trace_id_hex: str) -> None:
            self._path = output_path
            self._case_id = case_id
            self._trace_id_hex = trace_id_hex
            self._lock = RLock()
            self._path.parent.mkdir(parents=True, exist_ok=True)

        def export(self, spans: Any) -> SpanExportResult:
            lines: list[str] = []
            for span in spans:
                record = _span_to_record(span, case_id=self._case_id, trace_id_hex=self._trace_id_hex)
                lines.append(json.dumps(scrub_mapping(record), sort_keys=True, ensure_ascii=False))
            if lines:
                with self._lock:
                    with self._path.open("a", encoding="utf-8") as handle:
                        for line in lines:
                            handle.write(line + "\n")
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            return None

else:

    class _ScrubbingFileSpanExporter:  # type: ignore[no-redef]
        def __init__(self, output_path: Path, *, case_id: str, trace_id_hex: str) -> None:
            self._path = output_path
            self._case_id = case_id
            self._trace_id_hex = trace_id_hex
            self._lock = RLock()
            self._path.parent.mkdir(parents=True, exist_ok=True)

        def append_fallback_record(self, record: Dict[str, Any]) -> None:
            line = json.dumps(scrub_mapping(record), sort_keys=True, ensure_ascii=False)
            with self._lock:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")


def _span_to_record(span: Any, *, case_id: str, trace_id_hex: str) -> Dict[str, Any]:
    ctx = span.get_span_context()
    attributes = {}
    if hasattr(span, "attributes") and span.attributes:
        attributes = dict(span.attributes)
    events = []
    if hasattr(span, "events"):
        for event in span.events:
            events.append(
                {
                    "name": scrub_text(event.name),
                    "timestamp": event.timestamp,
                    "attributes": scrub_mapping(dict(event.attributes or {})),
                }
            )
    return {
        "case_id": case_id,
        "trace_id": trace_id_hex,
        "span_id": format(ctx.span_id, "016x"),
        "parent_span_id": format(getattr(span.parent, "span_id", 0) or 0, "016x"),
        "name": scrub_text(span.name),
        "kind": str(span.kind),
        "start_time": span.start_time,
        "end_time": span.end_time,
        "status": str(getattr(span.status, "status_code", "")),
        "attributes": scrub_mapping(attributes),
        "events": events,
    }


class CortexTracer:
    """Case-scoped tracer with local JSONL export (no remote collector by default)."""

    def __init__(self, *, case_id: str, output_dir: str | Path) -> None:
        if not str(case_id).strip():
            raise ValueError("case_id must be non-empty")
        self.case_id = str(case_id).strip()
        self.trace_id = case_id_to_trace_id(self.case_id)
        self.trace_id_hex = format(self.trace_id, "032x")
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.export_path = root / f"{self.case_id}_trace.jsonl"
        self._provider: Any = None
        self._tracer: Any = None
        self._exporter = _ScrubbingFileSpanExporter(
            self.export_path,
            case_id=self.case_id,
            trace_id_hex=self.trace_id_hex,
        )
        if _HAS_OTEL:
            resource = Resource.create({"service.name": "s3m-cortex", "case.id": self.case_id})
            provider = TracerProvider(resource=resource)
            processor = SimpleSpanProcessor(self._exporter)  # type: ignore[arg-type]
            provider.add_span_processor(processor)
            # Case-scoped provider (do not override the process-global TracerProvider).
            self._provider = provider
            self._tracer = provider.get_tracer("s3m.cortex", "1.0.0")

    def local_export(self) -> LocalTraceExport:
        return LocalTraceExport(path=self.export_path, case_id=self.case_id, trace_id_hex=self.trace_id_hex)

    @contextmanager
    def span(
        self,
        name: str,
        *,
        stage: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Start a pipeline span; attributes are scrubbed before export."""
        attrs = scrub_mapping(dict(attributes or {}))
        attrs["cortex.stage"] = stage
        attrs["case.id"] = self.case_id
        if not _HAS_OTEL:
            import time

            start = time.time_ns()
            yield attrs
            self._exporter.append_fallback_record(
                {
                    "case_id": self.case_id,
                    "trace_id": self.trace_id_hex,
                    "span_id": format(start % (2**64), "016x"),
                    "parent_span_id": "0000000000000000",
                    "name": scrub_text(name),
                    "kind": "INTERNAL",
                    "start_time": start,
                    "end_time": time.time_ns(),
                    "status": "OK",
                    "attributes": attrs,
                    "events": [],
                }
            )
            return

        parent_ctx = _case_root_context(self.trace_id)
        with trace.use_span(NonRecordingSpan(parent_ctx)):
            with self._tracer.start_as_current_span(
                scrub_text(name),
                kind=SpanKind.INTERNAL,
                attributes=attrs,
            ):
                yield attrs

    def force_flush(self) -> None:
        if self._provider is not None:
            self._provider.force_flush()


def _case_root_context(trace_id: int) -> SpanContext:
    return SpanContext(
        trace_id=trace_id,
        span_id=0,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )


def verify_trace_matches_case(export: LocalTraceExport) -> bool:
    """Ensure every exported line carries the same trace id as the case."""
    text = export.read_text()
    if not text.strip():
        return True
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("trace_id") != export.trace_id_hex:
            return False
        if payload.get("case_id") != export.case_id:
            return False
    return True
