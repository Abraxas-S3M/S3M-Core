"""Unit tests for threat dashboard provider."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.runtime_store import reset_runtime_state, set_sensors, set_threats
from src.dashboard.providers.threat_dash_provider import ThreatDashProvider


def setup_function() -> None:
    reset_runtime_state()


def test_get_threat_feed_required_fields() -> None:
    set_threats(
        [
            {
                "event_id": "t-1",
                "timestamp": "2026-03-31T10:00:00+00:00",
                "level": "HIGH",
                "category": "CYBER",
                "source": "MANUAL",
                "title": "Threat",
                "description": "desc",
                "confidence": 0.9,
                "location": {"x": 10, "y": 20, "z": 1},
            }
        ]
    )
    provider = ThreatDashProvider()
    feed = provider.get_threat_feed()
    assert isinstance(feed, list)
    assert feed
    first = feed[0]
    for key in ("id", "timestamp", "level", "category", "source", "title", "description", "confidence", "position"):
        assert key in first


def test_get_threat_stats_has_breakdowns() -> None:
    set_threats(
        [
            {"event_id": "t-1", "level": "HIGH", "category": "CYBER", "source": "MANUAL", "title": "a", "description": "d", "timestamp": "2026-03-31T10:00:00+00:00"},
            {"event_id": "t-2", "level": "CRITICAL", "category": "KINETIC", "source": "NETWORK_IDS", "title": "b", "description": "d", "timestamp": "2026-03-31T10:05:00+00:00"},
        ]
    )
    provider = ThreatDashProvider()
    stats = provider.get_threat_stats()
    assert "by_level" in stats
    assert "by_category" in stats
    assert "by_source" in stats


def test_get_threat_heatmap_shape() -> None:
    set_threats(
        [
            {"event_id": "t-1", "level": "HIGH", "category": "CYBER", "source": "MANUAL", "title": "a", "description": "d", "location": {"x": 120, "y": 190, "z": 0}, "timestamp": "2026-03-31T10:00:00+00:00"},
            {"event_id": "t-2", "level": "MEDIUM", "category": "CYBER", "source": "MANUAL", "title": "b", "description": "d", "location": {"x": 140, "y": 210, "z": 0}, "timestamp": "2026-03-31T10:01:00+00:00"},
        ]
    )
    provider = ThreatDashProvider()
    heat = provider.get_threat_heatmap()
    assert isinstance(heat, list)
    assert heat
    assert "position" in heat[0]
    assert "intensity" in heat[0]


def test_get_sensor_health_returns_list() -> None:
    set_sensors([{"sensor_id": "s-1", "type": "RADAR", "status": "active", "last_reading_time": "2026-03-31T10:00:00+00:00", "readings_count": 5}])
    provider = ThreatDashProvider()
    sensors = provider.get_sensor_health()
    assert isinstance(sensors, list)
    assert sensors

