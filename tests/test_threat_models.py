#!/usr/bin/env python3
"""Tests for threat detection domain models."""

from datetime import datetime, timezone

from src.threat_detection.models import (
    DetectionResult,
    ThreatCategory,
    ThreatEvent,
    ThreatLevel,
    ThreatSource,
)


def test_threat_event_creation_to_dict_and_prompt():
    event = ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.HIGH,
        category=ThreatCategory.CYBER,
        title="Operator detected suspicious beaconing",
        description="Outbound encrypted sessions exceed baseline.",
        raw_data={"session_count": 42},
        confidence=0.91,
        location={"sector": "ALPHA-3"},
        asset_ids=["node-17"],
    )

    payload = event.to_dict()
    prompt = event.to_prompt()

    assert payload["source"] == "MANUAL"
    assert payload["level"] == "HIGH"
    assert payload["category"] == "CYBER"
    assert payload["title"] == event.title
    assert "TACTICAL THREAT EVENT" in prompt
    assert event.event_id in prompt


def test_threat_level_ordering():
    assert ThreatLevel.CRITICAL > ThreatLevel.HIGH > ThreatLevel.MEDIUM > ThreatLevel.LOW > ThreatLevel.INFO


def test_detection_result_construction():
    event = ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.LOW,
        category=ThreatCategory.UNKNOWN,
        title="Routine event",
        description="No immediate action required.",
    )
    result = DetectionResult(
        source=ThreatSource.MANUAL,
        processing_time_ms=5.2,
        total_events=1,
        events_by_level={"LOW": 1},
        events=[event],
    )
    payload = result.to_dict()
    assert payload["source"] == "MANUAL"
    assert payload["total_events"] == 1
    assert payload["events_by_level"]["LOW"] == 1
