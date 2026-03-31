"""Unit tests for alert manager aggregation behavior."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.alert_manager import AlertManager
from src.dashboard.providers.runtime_store import reset_runtime_state, set_decisions, set_threats


def _seed_alert_data() -> None:
    set_threats(
        [
            {
                "event_id": "t1",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "level": "CRITICAL",
                "category": "CYBER",
                "source": "NETWORK_IDS",
                "title": "Critical net event",
                "description": "desc",
                "confidence": 0.9,
                "location": {"x": 100, "y": 120, "z": 0},
            },
            {
                "event_id": "t2",
                "timestamp": "2026-01-01T00:01:00+00:00",
                "level": "HIGH",
                "category": "KINETIC",
                "source": "SENSOR_FUSION",
                "title": "High kinetic event",
                "description": "desc",
                "confidence": 0.8,
                "location": {"x": 130, "y": 155, "z": 0},
            },
        ]
    )
    set_decisions(
        [
            {
                "id": "d1",
                "type": "target_prioritization",
                "agent_id": "agent-1",
                "confidence": 0.9,
                "risk_score": 0.9,
                "requires_review": True,
                "reasoning": "High risk action needs approval.",
                "timestamp": "2026-01-01T00:02:00+00:00",
                "status": "pending",
            }
        ]
    )


def test_collect_returns_unified_alert_list() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=500)
    alerts = manager.collect()
    assert isinstance(alerts, list)
    assert all("alert_id" in a for a in alerts)


def test_alerts_sorted_by_severity() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=500)
    alerts = manager.collect()
    levels = [a["level"] for a in alerts]
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    assert levels == sorted(levels, key=lambda item: order.get(item, 99))


def test_deduplication_same_alert_once() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=500)
    first = manager.collect()
    second = manager.collect()
    assert len(second) == len(first)
    assert len({a["alert_id"] for a in second}) == len(second)


def test_dismiss_removes_alert() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=500)
    alerts = manager.collect()
    assert alerts
    first_id = alerts[0]["alert_id"]
    manager.dismiss(first_id)
    remaining = manager.collect()
    assert all(a["alert_id"] != first_id for a in remaining)


def test_get_alert_counts_shape() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=500)
    manager.collect()
    counts = manager.get_alert_counts()
    assert "critical" in counts
    assert "high" in counts
    assert "medium" in counts
    assert "total" in counts


def test_max_alerts_fifo_rotation() -> None:
    reset_runtime_state()
    _seed_alert_data()
    manager = AlertManager(max_alerts=1)
    alerts = manager.collect()
    assert len(alerts) == 1
