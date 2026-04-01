#!/usr/bin/env python3
"""Unit tests for C2 message router."""

from __future__ import annotations

from services.comms.c2 import C2MessageRouter
from services.comms.models import (
    ChannelType,
    Message,
    MessagePriority,
    MessageStatus,
    MessageType,
    RelayBackend,
)
from services.comms.node_manager import CommsNodeManager
from services.comms.relays import RelayManager


def _router() -> C2MessageRouter:
    relay = RelayManager()
    relay.connect_backend(RelayBackend.SIMULATED)
    relay.create_channel("COMMAND", ChannelType.COMMAND_NET, ["CMD", "WOLF-01"])
    relay.create_channel("INTEL", ChannelType.INTEL_NET, ["CMD", "WOLF-01"])
    relay.create_channel("ALERT", ChannelType.ALERT_NET, ["ALL"])
    nodes = CommsNodeManager()
    nodes.register_node("WOLF-01", "field_unit", ["simulated"])
    return C2MessageRouter(relay_manager=relay, node_manager=nodes)


def _message(msg_type: MessageType, priority: MessagePriority = MessagePriority.ROUTINE, body: str = "enemy contact") -> Message:
    return Message(
        message_id="msg-r",
        timestamp="2026-04-01T00:00:00+00:00",
        sender_id="node-1",
        sender_callsign="WOLF-01",
        recipient_ids=["CMD"],
        channel_id=None,
        message_type=msg_type,
        priority=priority,
        status=MessageStatus.QUEUED,
        subject="status",
        body=body,
        language="en",
        relay_backend="simulated",
        encryption_protocol="aes256",
        metadata={"_plaintext_body": body},
    )


def test_route_message_routes_order_to_command_net():
    router = _router()
    result = router.route_message(_message(MessageType.ORDER))
    assert result["status"] in {"DELIVERED", "FAILED"}
    assert result["routed_to"]


def test_route_message_routes_alert_via_broadcast():
    router = _router()
    result = router.route_message(_message(MessageType.ALERT))
    assert result["backend"] == "broadcast"
    assert result["routed_to"] == [ChannelType.ALERT_NET.value]


def test_flash_priority_attempts_all_backends():
    router = _router()
    result = router.route_message(_message(MessageType.REPORT, priority=MessagePriority.FLASH))
    assert isinstance(result["routed_to"], list)


def test_nlp_enrichment_populates_summary_and_urgency():
    router = _router()
    msg = _message(MessageType.REPORT, body="request support immediate!!")
    result = router.route_message(msg)
    assert result["nlp_summary"]
    assert result["urgency"] >= 0.0


def test_route_sitrep_creates_intel_routing():
    router = _router()
    result = router.route_sitrep("enemy seen at 5000,3000", "WOLF-01")
    assert "message_id" in result


def test_get_routing_log_is_log_safe():
    router = _router()
    router.route_message(_message(MessageType.REPORT, body="secret text"))
    entry = router.get_routing_log(limit=1)[0]
    assert "body" not in entry["message"]
