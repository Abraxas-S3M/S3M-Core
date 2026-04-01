#!/usr/bin/env python3
"""Tests for simulated relay backend behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.comms.models import ChannelType, Message, MessagePriority, MessageStatus, MessageType, RelayStatus
from services.comms.relays.simulated_relay import SimulatedRelay


def _msg(body: str, channel_id: str = "direct") -> Message:
    return Message.create(
        sender_id="node-1",
        sender_callsign="EAGLE-01",
        recipient_ids=["node-2"],
        body=body,
        message_type=MessageType.REPORT,
        priority=MessagePriority.ROUTINE,
        channel_id=channel_id,
    )


def test_connect_always_true():
    relay = SimulatedRelay()
    assert relay.connect() is True


def test_send_receive_round_trip():
    relay = SimulatedRelay()
    relay.connect()
    m = _msg("test round trip", channel_id="chan-a")
    assert relay.send(m) is True
    out = relay.receive("chan-a")
    assert len(out) == 1
    assert out[0].body == "test round trip"
    assert out[0].status == MessageStatus.DELIVERED


def test_create_channel_and_list_channels():
    relay = SimulatedRelay()
    relay.connect()
    ch = relay.create_channel("Command", ChannelType.COMMAND_NET, ["n1", "n2"])
    listed = relay.list_channels()
    assert ch.channel_id in [c.channel_id for c in listed]


def test_broadcast_multiple_channels():
    relay = SimulatedRelay()
    relay.connect()
    c1 = relay.create_channel("C1", ChannelType.ALERT_NET, ["n1"])
    c2 = relay.create_channel("C2", ChannelType.ALERT_NET, ["n2"])
    result = relay.broadcast(_msg("alert"), [c1.channel_id, c2.channel_id])
    assert result[c1.channel_id] is True
    assert result[c2.channel_id] is True
    assert len(relay.receive(c1.channel_id)) == 1
    assert len(relay.receive(c2.channel_id)) == 1


def test_receive_since_filter():
    relay = SimulatedRelay()
    relay.connect()
    relay.send(_msg("older", "chan-b"))
    since = datetime.now(timezone.utc)
    relay.send(_msg("newer", "chan-b"))
    out = relay.receive("chan-b", since=since)
    assert len(out) == 1
    assert out[0].body == "newer"


def test_get_status_online():
    relay = SimulatedRelay()
    assert relay.get_status() == RelayStatus.ONLINE
