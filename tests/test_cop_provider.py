"""Unit tests for COPDataProvider."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.cop_provider import COPDataProvider
from src.dashboard.providers.runtime_store import reset_runtime_state, set_agents


class _FakeSwarm:
    def get_agents(self):  # noqa: D401
        return [
            {"id": "a1", "role": "LEADER", "state": "ACTIVE", "position": (10, 20, 3), "battery": 88},
            {"id": "a2", "role": "SCOUT", "state": "IDLE", "position": (30, 40, 5), "battery": 76},
            {"id": "a3", "role": "INTERCEPTOR", "state": "ACTIVE", "position": (50, 60, 8), "battery": 67},
            {"id": "a4", "role": "FOLLOWER", "state": "ACTIVE", "position": (70, 80, 1), "battery": 90},
            {"id": "a5", "role": "OTHER", "state": "ACTIVE", "position": (90, 20, 0), "battery": 45},
        ]


class _FakeThreatManager:
    def get_threats(self, limit=100):  # noqa: D401
        return [
            {
                "event_id": "t1",
                "level": "CRITICAL",
                "category": "KINETIC",
                "location": {"x": 1, "y": 2, "z": 0},
                "title": "Critical test threat",
                "timestamp": "2026-03-31T00:00:00+00:00",
                "confidence": 0.9,
            },
            {
                "event_id": "t2",
                "level": "HIGH",
                "category": "CYBER",
                "location": {"x": 3, "y": 4, "z": 0},
                "title": "High test threat",
                "timestamp": "2026-03-31T00:01:00+00:00",
                "confidence": 0.8,
            },
        ][:limit]


def setup_function() -> None:
    reset_runtime_state()


def test_get_cop_data_returns_expected_keys() -> None:
    provider = COPDataProvider()
    data = provider.get_cop_data()
    for key in ["agents", "threats", "tracks", "paths"]:
        assert key in data


def test_get_agents_returns_list_when_unavailable() -> None:
    set_agents([{"id": "r1", "role": "LEADER", "state": "ACTIVE", "position": (1, 2, 3), "battery": 50}])
    provider = COPDataProvider()
    provider._swarm_cls = None  # force fallback path
    agents = provider.get_agents()
    assert isinstance(agents, list)


def test_get_threats_returns_color_field() -> None:
    provider = COPDataProvider()
    provider._threat_cls = _FakeThreatManager
    threats = provider.get_threats()
    assert isinstance(threats, list)
    assert threats
    assert "color" in threats[0]


def test_icon_type_mapping() -> None:
    provider = COPDataProvider()
    provider._swarm_cls = _FakeSwarm
    icons = {a["role"]: a["icon_type"] for a in provider.get_agents()}
    assert icons["LEADER"] == "star"
    assert icons["SCOUT"] == "eye"
    assert icons["INTERCEPTOR"] == "crosshair"
    assert icons["FOLLOWER"] == "circle"
    assert icons["OTHER"] == "triangle"


def test_threat_color_mapping() -> None:
    provider = COPDataProvider()
    provider._threat_cls = _FakeThreatManager
    mapping = {t["level"]: t["color"] for t in provider.get_threats()}
    assert mapping["CRITICAL"] == "#ff0000"
    assert mapping["HIGH"] == "#ff6600"
