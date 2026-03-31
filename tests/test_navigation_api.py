#!/usr/bin/env python3
"""API tests for S3M Phase 8 navigation routes."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import app


def test_navigation_status():
    client = TestClient(app)
    response = client.get("/navigation/status")
    assert response.status_code == 200


def test_navigation_pose():
    client = TestClient(app)
    response = client.get("/navigation/pose")
    assert response.status_code == 200
    payload = response.json()
    assert "position" in payload


def test_navigation_gps_status():
    client = TestClient(app)
    response = client.get("/navigation/gps/status")
    assert response.status_code == 200


def test_navigation_plan():
    client = TestClient(app)
    response = client.post(
        "/navigation/plan",
        json={
            "start": [0.0, 0.0, 10.0],
            "goal": [50.0, 50.0, 10.0],
            "obstacles": [{"position": [25.0, 25.0, 10.0], "radius": 6.0}],
            "planner_type": "rrt_star",
            "platform_type": "quadrotor",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "path" in payload
    assert "trajectory" in payload


def test_navigation_waypoint_plan():
    client = TestClient(app)
    response = client.post(
        "/navigation/plan/waypoints",
        json={
            "waypoints": [
                {"position": [0.0, 0.0, 10.0], "radius": 2.0},
                {"position": [20.0, 10.0, 10.0], "radius": 2.0},
                {"position": [40.0, 20.0, 10.0], "radius": 2.0},
            ],
            "platform_type": "quadrotor",
        },
    )
    assert response.status_code == 200
    assert "plan_id" in response.json()


def test_navigation_edge_status():
    client = TestClient(app)
    response = client.get("/navigation/edge/status")
    assert response.status_code == 200


def test_navigation_jetson_health():
    client = TestClient(app)
    response = client.get("/navigation/jetson/health")
    assert response.status_code == 200
    payload = response.json()
    assert "gpu_utilization_pct" in payload


def test_navigation_jetson_capabilities():
    client = TestClient(app)
    response = client.get("/navigation/jetson/capabilities")
    assert response.status_code == 200
