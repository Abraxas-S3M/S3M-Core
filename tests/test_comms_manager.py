#!/usr/bin/env python3
"""Tests for top-level CommsManager pipeline integration."""

from __future__ import annotations

from services.comms import CommsManager
from services.comms.models import ChannelType, MessagePriority, MessageType, NodeType, RelayBackend


def _setup_manager() -> CommsManager:
    manager = CommsManager()
    manager.register_node("COMMAND-ALPHA", NodeType.COMMAND_CENTER, [RelayBackend.SIMULATED], (0.0, 0.0, 0.0))
    manager.register_node("WOLF-01", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED], (1.0, 1.0, 0.0))
    manager.create_channel("COMMAND-NET", ChannelType.COMMAND_NET, ["COMMAND-ALPHA", "WOLF-01"])
    manager.create_channel("INTEL-NET", ChannelType.INTEL_NET, ["COMMAND-ALPHA", "WOLF-01"])
    manager.create_channel("ALERT-NET", ChannelType.ALERT_NET, ["COMMAND-ALPHA", "WOLF-01"])
    return manager


def test_send_message_full_pipeline():
    manager = _setup_manager()
    result = manager.send_message(
        sender_callsign="COMMAND-ALPHA",
        recipients=["WOLF-01"],
        body="Enemy contact at grid 5000,3000 request support!",
        message_type=MessageType.REPORT,
        priority=MessagePriority.PRIORITY,
    )
    assert "message_id" in result
    assert "intel" in result
    assert "threat_indicators" in result["intel"]


def test_send_order_creates_order_type_message():
    manager = _setup_manager()
    result = manager.send_order(
        sender="COMMAND-ALPHA",
        recipients=["WOLF-01"],
        order_text="Move to sector Alpha and hold.",
        priority=MessagePriority.PRIORITY,
    )
    assert result["status"] in {"DELIVERED", "FAILED"}


def test_broadcast_alert_sends_flash_priority():
    manager = _setup_manager()
    result = manager.broadcast_alert("COMMAND-ALPHA", "IED threat on Route Bravo!")
    assert result["urgency"] >= 0.9


def test_receive_messages_returns_enriched_messages_with_summaries():
    manager = _setup_manager()
    manager.send_message(
        sender_callsign="COMMAND-ALPHA",
        recipients=["WOLF-01"],
        body="Routine logistics update.",
        message_type=MessageType.LOGISTIC,
        priority=MessagePriority.ROUTINE,
    )
    messages = manager.receive_messages(channel_id=None)
    if messages:
        assert messages[-1].summary is not None


def test_get_comms_brief_returns_non_empty_string():
    manager = _setup_manager()
    brief = manager.get_comms_brief(minutes=60)
    assert isinstance(brief, str)
    assert len(brief) > 0


def test_get_network_status_includes_all_subsystem_info():
    manager = _setup_manager()
    status = manager.get_network_status()
    for key in ("relay", "nodes", "message_stats", "nlp"):
        assert key in status


def test_health_check_returns_expected_keys():
    manager = _setup_manager()
    health = manager.health_check()
    for key in ("relay_manager", "nlp", "c2_router", "node_manager", "message_log_size"):
        assert key in health
