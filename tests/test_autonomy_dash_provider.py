"""Unit tests for autonomy dashboard provider."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.autonomy_dash_provider import AutonomyDashProvider
from src.dashboard.providers.runtime_store import reset_runtime_state, set_agents, set_decisions, set_formation, set_missions


def setup_function() -> None:
    reset_runtime_state()
    set_agents(
        [
            {
                "id": "agent-1",
                "role": "LEADER",
                "state": "ACTIVE",
                "position": (100, 100, 20),
                "battery": 91,
                "capability": "uav",
                "mission_name": "M1",
                "last_heartbeat": "2026-03-31T00:00:00+00:00",
            }
        ]
    )
    set_missions(
        [
            {
                "id": "m1",
                "type": "recon",
                "status": "active",
                "assigned_agents": ["agent-1"],
                "progress_pct": 44.0,
                "duration": 120.0,
                "waypoints_completed": 2,
            }
        ]
    )
    set_formation({"type": "WEDGE", "spacing": 40, "positions": {"agent-1": "leader"}, "score": 0.8})
    set_decisions(
        [
            {
                "id": "d1",
                "type": "route",
                "agent_id": "agent-1",
                "confidence": 0.8,
                "risk_score": 0.6,
                "requires_review": True,
                "reasoning": "reroute around threat",
                "timestamp": "2026-03-31T00:05:00+00:00",
                "status": "pending",
                "context": "demo",
            },
            {
                "id": "d2",
                "type": "hold",
                "agent_id": "agent-1",
                "confidence": 0.9,
                "risk_score": 0.2,
                "requires_review": False,
                "reasoning": "maintain position",
                "timestamp": "2026-03-31T00:06:00+00:00",
                "status": "approved",
                "context": "demo",
            },
        ]
    )


def test_agent_roster_has_calculated_fields() -> None:
    provider = AutonomyDashProvider()
    roster = provider.get_agent_roster()
    assert isinstance(roster, list)
    assert "time_since_heartbeat" in roster[0]
    assert "mission_name" in roster[0]
    assert "formation_position" in roster[0]


def test_get_missions_returns_list() -> None:
    provider = AutonomyDashProvider()
    missions = provider.get_missions()
    assert isinstance(missions, list)
    assert missions[0]["id"] == "m1"


def test_review_queue_only_requires_review() -> None:
    provider = AutonomyDashProvider()
    queue = provider.get_review_queue()
    assert isinstance(queue, list)
    assert len(queue) == 1
    assert queue[0]["id"] == "d1"
    assert queue[0]["requires_review"] is True


def test_send_nl_command_returns_parsed_command() -> None:
    provider = AutonomyDashProvider()
    result = provider.send_nl_command("hold position", language="en")
    assert result["status"] == "ok"
    assert "parsed_command" in result
    assert result["parsed_command"]["command"] == "hold_position"


def test_get_formation_data_fields() -> None:
    provider = AutonomyDashProvider()
    data = provider.get_formation_data()
    assert "type" in data
    assert "positions" in data
    assert "formation_score" in data
