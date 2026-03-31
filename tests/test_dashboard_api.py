"""Integration tests for Layer 06 dashboard API endpoints."""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import app
from src.dashboard.providers.runtime_store import reset_runtime_state


def setup_function() -> None:
    reset_runtime_state()


def test_dashboard_status_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/status")
    assert resp.status_code == 200


def test_dashboard_overview_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/overview")
    assert resp.status_code == 200
    data = resp.json()
    for key in ["llm", "threats", "autonomy", "simulation", "navigation", "system"]:
        assert key in data


def test_dashboard_cop_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/cop")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert "threats" in data


def test_dashboard_llm_status_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/llm/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "engines" in data
    assert len(data["engines"]) == 4


def test_dashboard_threat_feed_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/threats/feed")
    assert resp.status_code == 200


def test_dashboard_threat_stats_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/threats/stats")
    assert resp.status_code == 200


def test_dashboard_autonomy_agents_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/autonomy/agents")
    assert resp.status_code == 200


def test_dashboard_autonomy_review_queue_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/autonomy/decisions/review")
    assert resp.status_code == 200


def test_dashboard_autonomy_command_endpoint() -> None:
    client = TestClient(app)
    resp = client.post(
        "/dashboard/autonomy/command",
        json={"text": "hold position", "language": "en"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("status") == "ok"


def test_dashboard_system_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data


def test_dashboard_system_jetson_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/dashboard/system/jetson")
    assert resp.status_code == 200


def test_dashboard_alerts_endpoints() -> None:
    client = TestClient(app)
    resp_alerts = client.get("/dashboard/alerts")
    resp_counts = client.get("/dashboard/alerts/count")
    assert resp_alerts.status_code == 200
    assert resp_counts.status_code == 200
