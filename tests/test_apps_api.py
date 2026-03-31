"""API tests for Phase 11 domain application endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


client = TestClient(app)


def test_post_battle_opord_200():
    resp = client.post("/apps/battle/opord", json={"brief": "Patrol sector alpha and report threats."})
    assert resp.status_code == 200


def test_post_logistics_predict_200():
    payload = {
        "records": [
            {"id": "s1", "delay_hours": 1, "weight": 100, "priority": 1, "route_distance": 120},
            {"id": "s2", "delay_hours": 8, "weight": 80, "priority": 3, "route_distance": 220},
        ]
    }
    resp = client.post("/apps/logistics/predict", json=payload)
    assert resp.status_code == 200


def test_post_logistics_route_200():
    resp = client.post(
        "/apps/logistics/route",
        json={"origin": [0, 0, 0], "destination": [100, 100, 0], "threats": []},
    )
    assert resp.status_code == 200


def test_post_threats_correlate_200():
    resp = client.post("/apps/threats/correlate", json={"events": []})
    assert resp.status_code == 200


def test_post_geopolitical_analyze_200():
    resp = client.post(
        "/apps/geopolitical/analyze",
        json={"description": "Naval standoff near chokepoint", "region": "Red Sea"},
    )
    assert resp.status_code == 200


def test_get_geopolitical_risks_200():
    resp = client.get("/apps/geopolitical/risks")
    assert resp.status_code == 200


def test_post_drone_mission_200():
    resp = client.post(
        "/apps/drone/mission",
        json={
            "mission_type": "PATROL",
            "waypoints": [[0, 0, 30], [50, 60, 30]],
            "num_agents": 1,
            "roe": "weapons_tight",
            "platform_type": "quadrotor",
        },
    )
    assert resp.status_code == 200


def test_get_data_datasets_200():
    resp = client.get("/apps/data/datasets")
    assert resp.status_code == 200
    assert isinstance(resp.json().get("datasets"), list)


def test_get_data_stats_200():
    resp = client.get("/apps/data/stats")
    assert resp.status_code == 200
