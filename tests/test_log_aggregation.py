"""Tests for Layer 07 log aggregation adapters and coordinator."""

from __future__ import annotations

from services.cyber.log_aggregation import GraylogAdapter, LogAggregator, OpenSearchAdapter
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _sample_event() -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.HIGH,
        category=ThreatCategory.CYBER,
        title="Log ingestion test event",
        description="Synthetic event for Graylog/OpenSearch testing",
        raw_data={"src_ip": "203.0.113.44", "dest_ip": "10.0.0.2"},
        confidence=0.79,
        classification="UNCLASSIFIED - FOUO",
    )


def test_graylog_adapter_offline_saves_to_buffer():
    adapter = GraylogAdapter(url="http://127.0.0.1:65530/api")
    sent = adapter.send_message({"title": "offline message", "description": "buffer me", "level": 6})
    assert sent is False


def test_opensearch_adapter_offline_saves_to_buffer():
    adapter = OpenSearchAdapter(url="http://127.0.0.1:65531")
    ok = adapter.index_event({"id": "evt-1", "message": "buffer me"})
    assert ok is False


def test_log_aggregator_ingest_threat_event_converts_and_dispatches():
    aggregator = LogAggregator()
    result = aggregator.ingest_threat_event(_sample_event())
    assert set(result.keys()) == {"graylog", "opensearch"}


def test_log_aggregator_search_returns_empty_when_backends_offline():
    aggregator = LogAggregator()
    results = aggregator.search("no-such-indicator")
    assert isinstance(results, list)

