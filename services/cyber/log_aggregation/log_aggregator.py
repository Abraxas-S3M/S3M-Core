"""Unified SOC log ingestion and query layer for Graylog/OpenSearch backends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.cyber.log_aggregation.graylog_adapter import GraylogAdapter
from services.cyber.log_aggregation.opensearch_adapter import OpenSearchAdapter
from services.cyber.models import IncidentCase


class LogAggregator:
    """Dispatches SOC events to logging backends with offline resiliency."""

    def __init__(self) -> None:
        self.graylog = GraylogAdapter()
        self.opensearch = OpenSearchAdapter()

    def _event_to_log(self, event: Any) -> dict:
        if hasattr(event, "to_dict"):
            payload = event.to_dict()
        elif isinstance(event, dict):
            payload = dict(event)
        else:
            payload = dict(getattr(event, "__dict__", {}))
        return {
            "event_id": payload.get("event_id", "unknown"),
            "title": payload.get("title", "Threat event"),
            "description": payload.get("description", ""),
            "level": str(payload.get("level", "INFO")),
            "category": str(payload.get("category", "UNKNOWN")),
            "source": str(payload.get("source", "UNKNOWN")),
            "raw_data": payload.get("raw_data", {}),
            "timestamp": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }

    def ingest_threat_event(self, event: Any) -> dict:
        entry = self._event_to_log(event)
        graylog_ok = self.graylog.send_message(entry)
        opensearch_ok = self.opensearch.index_event(entry)
        return {"graylog": bool(graylog_ok), "opensearch": bool(opensearch_ok)}

    def ingest_case(self, case: IncidentCase) -> dict:
        payload = case.to_dict()
        graylog_ok = self.graylog.send_message(
            {
                "event_id": case.case_id,
                "title": f"Case {case.case_id}",
                "description": case.description,
                "level": case.severity.value,
                "category": "CASE",
                "source": "SOC_CASE_MANAGER",
                "raw_data": payload,
            }
        )
        opensearch_ok = self.opensearch.index_event(payload, index="s3m-cases")
        return {"graylog": bool(graylog_ok), "opensearch": bool(opensearch_ok)}

    def ingest_audit_entry(self, entry: dict) -> dict:
        payload = dict(entry)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        graylog_ok = self.graylog.send_message(
            {
                "event_id": payload.get("id", payload.get("event_id", "audit-entry")),
                "title": payload.get("action", "audit"),
                "description": str(payload),
                "level": payload.get("level", "INFO"),
                "category": "AUDIT",
                "source": "SOC_AUDIT",
                "raw_data": payload,
            }
        )
        opensearch_ok = self.opensearch.index_event(payload, index="s3m-audit")
        return {"graylog": bool(graylog_ok), "opensearch": bool(opensearch_ok)}

    def search(self, query: str, backend: str = "all") -> List[dict]:
        target = backend.lower().strip()
        results: List[dict] = []
        if target in {"all", "graylog"}:
            results.extend(self.graylog.search(query))
        if target in {"all", "opensearch"}:
            results.extend(self.opensearch.search(query))
        return results

    def get_backend_status(self) -> dict:
        return {
            "graylog": self.graylog.connect(),
            "opensearch": self.opensearch.connect(),
        }
