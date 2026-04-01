"""Tests for Phase 16 C2SIM engine behaviors."""

from __future__ import annotations

from services.interop.c2sim.c2sim_engine import C2SIMEngine


def test_c2sim_engine_initializes_without_server():
    engine = C2SIMEngine(config={"server_url": None})
    health = engine.health_check()
    assert health["status"] == "operational"
    assert health["server"]["connected"] is False


def test_send_order_saves_to_outbox_when_offline():
    engine = C2SIMEngine(config={"server_url": None})
    response = engine.send_order(
        {
            "order_id": "ord-offline",
            "issuer": "HQ",
            "task_type": "Advance",
            "assigned_units": ["u-1"],
            "waypoints": [(24.7, 46.6, 0)],
            "roe": "self-defense",
        }
    )
    assert response["status"] == "queued_offline"
    assert "message_id" in response


def test_order_to_mission_produces_valid_dict():
    engine = C2SIMEngine()
    mission = engine.order_to_mission(
        {
            "order_id": "ord-1",
            "task_type": "Advance",
            "assigned_units": ["u-1", "u-2"],
            "waypoints": [(24.7, 46.6, 0), (24.8, 46.7, 0)],
            "roe": "self-defense",
        }
    )
    assert mission["mission_id"] == "ord-1"
    assert mission["mission_type"] == "ADVANCE"
    assert mission["agent_ids"] == ["u-1", "u-2"]
    assert len(mission["waypoints"]) == 2


def test_mission_to_order_produces_valid_xml():
    engine = C2SIMEngine()
    xml = engine.mission_to_order(
        {
            "mission_id": "msn-1",
            "mission_type": "RECON",
            "agent_ids": ["alpha"],
            "waypoints": [{"x": 1.0, "y": 2.0, "z": 3.0}],
            "rules_of_engagement": "SELF_DEFENSE_ONLY",
        }
    )
    assert "<Order" in xml
    assert "msn-1" in xml
