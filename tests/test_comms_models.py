#!/usr/bin/env python3
"""Unit tests for Layer 08 communications dataclasses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.comms.models import (
    Channel,
    ChannelType,
    CommsNode,
    Message,
    MessagePriority,
    MessageStatus,
    MessageSummary,
    MessageType,
    NodeType,
    RelayBackend,
)


def _sample_message(body: str = "Enemy contact near grid 5000,3000") -> Message:
    return Message(
        message_id="msg-001",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=2),
        sender_id="node-1",
        sender_callsign="EAGLE-01",
        recipient_ids=["node-2"],
        channel_id="ch-1",
        message_type=MessageType.REPORT,
        priority=MessagePriority.PRIORITY,
        status=MessageStatus.QUEUED,
        subject="SITREP",
        body=body,
        language="auto",
        relay_backend="simulated",
        encryption_protocol="none",
    )


def test_message_creation_to_dict_and_log_safe():
    msg = _sample_message()
    payload = msg.to_dict()
    assert payload["message_id"] == "msg-001"
    assert payload["body"] == "Enemy contact near grid 5000,3000"
    safe = msg.to_log_safe()
    assert "body" not in safe
    assert safe["body_redacted"] is True
    assert safe["body_length"] > 0


def test_message_is_arabic_detection():
    msg = _sample_message(body="رصد هدف معادي في القطاع")
    assert msg.is_arabic() is True
    msg2 = _sample_message(body="No Arabic text")
    assert msg2.is_arabic() is False


def test_message_priority_ordering():
    assert MessagePriority.FLASH > MessagePriority.IMMEDIATE
    assert MessagePriority.IMMEDIATE > MessagePriority.PRIORITY
    assert MessagePriority.PRIORITY > MessagePriority.ROUTINE
    assert MessagePriority.ROUTINE > MessagePriority.DEFERRED


def test_channel_creation_member_count():
    channel = Channel(
        channel_id="ch-1",
        name="COMMAND-NET",
        channel_type=ChannelType.COMMAND_NET,
        members=["node-1", "node-2", "node-3"],
        relay_backend="simulated",
        encryption_required=True,
        priority_default=MessagePriority.PRIORITY,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    assert channel.member_count() == 3
    assert channel.to_dict()["channel_type"] == "COMMAND_NET"


def test_comms_node_online_and_heartbeat_delta():
    node = CommsNode(
        node_id="node-1",
        callsign="WOLF-01",
        node_type=NodeType.FIELD_UNIT,
        relay_backends=[RelayBackend.SIMULATED],
        position=(1.0, 2.0, 3.0),
        last_heartbeat=datetime.now(timezone.utc),
        status="online",
        signal_strength=0.8,
        battery_pct=67.0,
    )
    assert node.is_online() is True
    assert node.time_since_heartbeat() >= 0.0


def test_message_summary_creation_all_fields():
    summary = MessageSummary(
        message_id="msg-1",
        original_language="ar",
        summary_ar="ملخص",
        summary_en="Summary",
        entities=[{"type": "threat", "value": "enemy", "confidence": 0.9}],
        intent="report_contact",
        urgency_score=0.8,
        sentiment="urgent",
        model_used="keyword_fallback",
        processing_time_ms=1.2,
    )
    payload = summary.to_dict()
    assert payload["intent"] == "report_contact"
    assert payload["urgency_score"] == 0.8


def test_message_age_seconds_computation():
    msg = _sample_message()
    assert msg.age_seconds() >= 2.0
