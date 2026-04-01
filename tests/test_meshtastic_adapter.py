#!/usr/bin/env python3
"""Tests for Meshtastic adapter offline behavior and truncation."""

from __future__ import annotations

from datetime import datetime, timezone

from services.comms.models import Message, MessagePriority, MessageStatus, MessageType, RelayStatus
from services.comms.relays.meshtastic_adapter import MeshtasticAdapter


def _message(body: str) -> Message:
    return Message(
        message_id="msg-mesh-01",
        timestamp=datetime.now(timezone.utc),
        sender_id="node-a",
        sender_callsign="WOLF-01",
        recipient_ids=["node-b"],
        channel_id="mesh-local",
        message_type=MessageType.REPORT,
        priority=MessagePriority.ROUTINE,
        status=MessageStatus.QUEUED,
        subject="Mesh report",
        body=body,
        language="en",
        relay_backend="meshtastic",
        encryption_protocol="none",
    )


def test_connect_false_when_meshtastic_unavailable() -> None:
    adapter = MeshtasticAdapter()
    assert adapter.connect() is False


def test_message_truncation_228_bytes() -> None:
    adapter = MeshtasticAdapter()
    text = "A" * 500
    truncated = adapter._truncate_text(text, max_bytes=228)
    assert len(truncated.encode("utf-8")) <= 228
    assert truncated.endswith("[TRUNCATED]")


def test_get_status_offline() -> None:
    adapter = MeshtasticAdapter()
    assert adapter.get_status() == RelayStatus.OFFLINE
