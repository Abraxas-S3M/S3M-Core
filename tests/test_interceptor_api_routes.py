"""Unit tests for interceptor FastAPI routes."""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client() -> TestClient:
    api_routes = importlib.import_module("services.interceptor.api_routes")
    api_routes = importlib.reload(api_routes)
    app = FastAPI()
    app.include_router(api_routes.router)
    return TestClient(app)


def test_register_assign_launch_and_list_active() -> None:
    client = _build_client()
    register = client.post("/interceptor/register", json={"name_en": "Falcon-1"})
    assert register.status_code == 200
    interceptor_id = register.json()["interceptor_id"]

    assign = client.post(
        "/interceptor/assign",
        json={"interceptor_id": interceptor_id, "target_id": "trk-01"},
    )
    assert assign.status_code == 200
    assert assign.json()["status"] == "assigned"

    launch = client.post(f"/interceptor/launch/{interceptor_id}")
    assert launch.status_code == 200
    assert launch.json()["status"] == "launched"

    active = client.get("/interceptor/active")
    assert active.status_code == 200
    payload = active.json()
    assert len(payload["interceptions"]) == 1
    assert payload["interceptions"][0]["interceptor_id"] == interceptor_id
    assert payload["interceptions"][0]["target_id"] == "trk-01"


def test_assign_rejects_missing_fields() -> None:
    client = _build_client()
    response = client.post("/interceptor/assign", json={"target_id": "trk-02"})
    assert response.status_code == 400
    assert "interceptor_id" in response.json()["detail"]


def test_register_rejects_invalid_position_shape() -> None:
    client = _build_client()
    response = client.post("/interceptor/register", json={"position": [0.0, 1.0]})
    assert response.status_code == 400
    assert "position" in response.json()["detail"]


def test_guide_rejects_when_not_active() -> None:
    client = _build_client()
    register = client.post("/interceptor/register", json={})
    interceptor_id = register.json()["interceptor_id"]

    guide = client.post(
        "/interceptor/guide",
        json={
            "interceptor_id": interceptor_id,
            "interceptor_position": [0.0, 0.0, 0.0],
            "interceptor_velocity": [100.0, 0.0, 0.0],
            "target_position": [1000.0, 0.0, 0.0],
            "target_velocity": [80.0, 0.0, 0.0],
        },
    )
    assert guide.status_code == 404
    assert "No active interception" in guide.json()["detail"]


def test_terminal_handoff_and_result_completion() -> None:
    client = _build_client()
    register = client.post("/interceptor/register", json={"terminal_range_m": 500.0, "handoff_range_m": 100.0})
    interceptor_id = register.json()["interceptor_id"]
    client.post("/interceptor/assign", json={"interceptor_id": interceptor_id, "target_id": "trk-03"})
    client.post(f"/interceptor/launch/{interceptor_id}")
    client.post(f"/interceptor/radar-acquired/{interceptor_id}")

    guide = client.post(
        "/interceptor/guide",
        json={
            "interceptor_id": interceptor_id,
            "interceptor_position": [0.0, 0.0, 0.0],
            "interceptor_velocity": [0.0, 0.0, 0.0],
            "target_position": [3.0, 0.0, 0.0],
            "target_velocity": [0.0, 0.0, 0.0],
        },
    )
    assert guide.status_code == 200
    guide_payload = guide.json()
    assert guide_payload["terminal_phase"] is True

    result = client.get(f"/interceptor/result/{interceptor_id}")
    assert result.status_code == 200
    result_payload = result.json()
    assert result_payload["status"] == "completed"
    assert result_payload["outcome"] == "intercepted"

