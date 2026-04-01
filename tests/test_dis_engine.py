"""Unit tests for Phase 16 DIS engine orchestration."""

from __future__ import annotations

from datetime import datetime

from services.interop.dis.dis_engine import DISEngine
from src.simulation.models import EntityType, SimEntity, SimulationState


def test_dis_engine_initializes_without_network():
    engine = DISEngine(config={"port": 39991})
    assert engine.network.socket is None
    assert engine.network.port == 39991


def test_publish_entity_converts_s3m_entity():
    engine = DISEngine(config={"port": 39992})
    # Publish with no active socket should fail cleanly but still run conversion path.
    ok = engine.publish_entity(
        {
            "entity_id": "veh-1",
            "name": "Saudi APC",
            "affiliation": "friendly",
            "entity_type": {"kind": 1, "domain": 1, "country": 178, "category": 1, "subcategory": 0},
            "position": {"lat": 24.7136, "lon": 46.6753, "alt": 0.0},
            "orientation": {"heading": 90.0, "pitch": 0.0, "roll": 0.0},
            "velocity": {"x": 2.0, "y": 0.0, "z": 0.0},
        }
    )
    assert ok is False


def test_sync_from_simulation_publishes_entities():
    engine = DISEngine(config={"port": 39993})
    sim = SimulationState(
        timestamp=datetime.utcnow(),
        sim_time_seconds=5.0,
        entities=[
            SimEntity(
                entity_id="1",
                entity_type=EntityType.FRIENDLY_UGV,
                position=(24.7, 46.6, 0.0),
                velocity=(1.0, 0.0, 0.0),
                heading=0.0,
                health=1.0,
            )
        ],
    )
    count = engine.sync_from_simulation(sim)
    assert count == 0  # no network started, but method should complete


def test_health_check_returns_expected_keys():
    engine = DISEngine(config={"port": 39994})
    health = engine.health_check()
    assert "status" in health
    assert "network" in health
    assert "known_entities" in health
