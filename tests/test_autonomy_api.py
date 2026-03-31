#!/usr/bin/env python3
"""API tests for Phase 6 autonomy endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.autonomy_routes import runtime
from src.api.server import app


client = TestClient(app)


def _register_agent(agent_id: str) -> None:
    client.post(
        "/autonomy/agents/register",
        json={
            "agent_id": agent_id,
            "role": "leader",
            "state": "idle",
            "capability": "air",
            "position": [0.0, 0.0, 0.0],
            "heading": 0.0,
            "speed": 0.0,
            "battery_pct": 90.0,
            "fuel_pct": 80.0,
            "sensor_loadout": ["eo"],
            "weapon_loadout": ["kinetic"],
            "comms_status": "nominal",
        },
    )


def test_register_agent() -> None:
    response = client.post(
        "/autonomy/agents/register",
        json={
            "agent_id": "api-agent-1",
            "role": "leader",
            "state": "idle",
            "capability": "air",
            "position": [10.0, 10.0, 10.0],
            "heading": 90.0,
            "speed": 5.0,
            "battery_pct": 95.0,
            "fuel_pct": 85.0,
            "sensor_loadout": ["eo"],
            "weapon_loadout": ["kinetic"],
            "comms_status": "nominal",
        },
    )
    assert response.status_code == 200
    assert response.json()["agent_id"] == "api-agent-1"


def test_get_agents_returns_list() -> None:
    _register_agent("api-agent-2")
    response = client.get("/autonomy/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_autonomy_status() -> None:
    response = client.get("/autonomy/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "rl" in data
    assert "swarm" in data
    assert "xai" in data


def test_issue_structured_swarm_command() -> None:
    response = client.post(
        "/autonomy/swarm/command",
        json={
            "command_type": "hold",
            "target_agents": ["all"],
            "parameters": {},
            "issued_by": "operator",
            "priority": 3,
            "ttl_seconds": 60.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_issue_nl_command() -> None:
    response = client.post(
        "/autonomy/swarm/command/nl",
        json={"natural_language": "hold position", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_decisions_returns_list() -> None:
    response = client.get("/autonomy/decisions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_emergency_stop() -> None:
    response = client.post("/autonomy/swarm/emergency-stop")
    assert response.status_code == 200
    assert response.json()["command"]["command_type"] == "emergency_stop"

