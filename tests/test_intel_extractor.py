#!/usr/bin/env python3
"""Tests for comms-derived intelligence extraction."""

from datetime import datetime, timezone

from services.comms.c2.intel_extractor import MessageIntelExtractor
from services.comms.models import Message, MessagePriority, MessageStatus, MessageType


def _message(body: str, intent: str | None = None) -> Message:
    return Message(
        message_id="msg-intel",
        timestamp=datetime.now(timezone.utc),
        sender_id="n1",
        sender_callsign="WOLF-01",
        recipient_ids=["hq"],
        channel_id="sim-1",
        message_type=MessageType.REPORT,
        priority=MessagePriority.PRIORITY,
        status=MessageStatus.QUEUED,
        subject="Intel",
        body=body,
        language="auto",
        relay_backend="simulated",
        encryption_protocol="none",
        extracted_intent=intent,
    )


def test_extract_finds_threat_indicators_enemy_uav():
    extractor = MessageIntelExtractor()
    result = extractor.extract(_message("enemy UAV detected over ridge"))
    assert len(result["threat_indicators"]) >= 1


def test_extract_finds_arabic_threat():
    extractor = MessageIntelExtractor()
    result = extractor.extract(_message("عدو مسلح في المنطقة"))
    assert len(result["threat_indicators"]) >= 1


def test_extract_position_reports_from_grid():
    extractor = MessageIntelExtractor()
    result = extractor.extract(_message("contact at 5000,3000 moving east"))
    assert any(e.get("type") == "location" for e in result["position_reports"])


def test_extract_support_requests_from_intent():
    extractor = MessageIntelExtractor()
    result = extractor.extract(_message("we need reinforcement", intent="request_support"))
    assert len(result["support_requests"]) == 1


def test_feed_to_threat_detection_creates_events():
    extractor = MessageIntelExtractor()
    created = extractor.feed_to_threat_detection(
        [{"keyword": "enemy", "message_id": "m1", "callsign": "WOLF-01", "classification": "UNCLASSIFIED - FOUO"}]
    )
    assert isinstance(created, list)
