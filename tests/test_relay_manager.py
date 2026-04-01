#!/usr/bin/env python3
"""Tests for relay manager backend coordination and fallback behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from services.comms.models import ChannelType, Message, MessagePriority, MessageStatus, MessageType, RelayBackend
from services.comms.relays import RelayManager


def _message(channel_id: str = "direct") -> Message:
    return Message(
        message_id="msg-relay",
        timestamp=datetime.now(timezone.utc),
        sender_id="n1",
        sender_callsign="EAGLE-01",
        recipient_ids=["n2"],
        channel_id=channel_id,
        message_type=MessageType.REPORT,
        priority=MessagePriority.ROUTINE,
        status=MessageStatus.QUEUED,
        subject="status",
        body="routine update",
        language="en",
        relay_backend="simulated",
        encryption_protocol="none",
    )


def test_fallback_chain_with_simulated_only():
    manager = RelayManager()
    msg = _message()
    assert manager.send(msg) is True
    assert msg.relay_backend == RelayBackend.SIMULATED.value


def test_get_backend_status_includes_simulated_online():
    manager = RelayManager()
    status = manager.get_backend_status()
    assert status["simulated"].value == "ONLINE"
    assert status["matrix"].value in {"OFFLINE", "ONLINE"}


def test_broadcast_sends_to_channel_type():
    manager = RelayManager()
    ch = manager.create_channel("ALERT-NET", ChannelType.ALERT_NET, ["u1", "u2"])
    msg = _message(channel_id=ch.channel_id)
    result = manager.broadcast(msg, channel_type=ChannelType.ALERT_NET)
    assert result["attempted"] >= 1
    assert result["delivered"] >= 1


def test_create_channel_default_backend():
    manager = RelayManager()
    channel = manager.create_channel("COMMAND", ChannelType.COMMAND_NET, ["c1"])
    assert channel.relay_backend == "simulated"


def test_receive_returns_messages_from_connected_backend():
    manager = RelayManager()
    msg = _message("direct")
    manager.send(msg)
    received = manager.receive("direct")
    assert len(received) >= 1
