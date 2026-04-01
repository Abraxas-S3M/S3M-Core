#!/usr/bin/env python3
"""Tests for comms node manager."""

from datetime import datetime, timedelta, timezone

from services.comms.models import NodeType, RelayBackend
from services.comms.node_manager import CommsNodeManager


def test_register_node_and_get_node():
    manager = CommsNodeManager()
    node = manager.register_node("EAGLE-01", NodeType.UAV_PLATFORM, [RelayBackend.SIMULATED])
    assert manager.get_node(node.node_id) is not None


def test_get_node_by_callsign():
    manager = CommsNodeManager()
    manager.register_node("WOLF-01", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED])
    assert manager.get_node_by_callsign("wolf-01") is not None


def test_heartbeat_updates_last_heartbeat():
    manager = CommsNodeManager()
    node = manager.register_node("NODE-1", NodeType.RELAY_NODE, [RelayBackend.SIMULATED])
    old = node.last_heartbeat
    manager.heartbeat(node.node_id)
    assert manager.get_node(node.node_id).last_heartbeat >= old


def test_detect_lost_nodes():
    manager = CommsNodeManager()
    node = manager.register_node("NODE-2", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED])
    node.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=400)
    lost = manager.detect_lost_nodes(timeout_seconds=300)
    assert any(n.node_id == node.node_id for n in lost)


def test_get_network_topology():
    manager = CommsNodeManager()
    manager.register_node("A", NodeType.COMMAND_CENTER, [RelayBackend.SIMULATED, RelayBackend.MESHTASTIC])
    manager.register_node("B", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED])
    topo = manager.get_network_topology()
    assert "nodes" in topo
    assert "links" in topo
