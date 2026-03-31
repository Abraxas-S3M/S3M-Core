#!/usr/bin/env python3
"""API tests for S3M Phase 5 threat and sensor routes."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from src.api.server import app


def test_manual_threat_ingest():
    client = TestClient(app)
    response = client.post(
        "/threats/ingest/manual",
        json={
            "title": "Operator report",
            "description": "Suspicious RF interference near sector delta.",
            "level": "HIGH",
            "category": "ELECTRONIC_WARFARE",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "event" in data
    assert data["event"]["title"] == "Operator report"


def test_get_threats_returns_list():
    client = TestClient(app)
    response = client.get("/threats")
    assert response.status_code == 200
    payload = response.json()
    assert "events" in payload
    assert isinstance(payload["events"], list)


def test_get_threat_stats():
    client = TestClient(app)
    response = client.get("/threats/stats")
    assert response.status_code == 200
    payload = response.json()
    assert "total_events" in payload
    assert "events_by_level" in payload


def test_get_sitrep():
    client = TestClient(app)
    response = client.get("/threats/sitrep")
    assert response.status_code == 200
    payload = response.json()
    assert "sitrep" in payload
    assert isinstance(payload["sitrep"], str)


def test_sensor_register():
    client = TestClient(app)
    response = client.post(
        "/sensors/register",
        json={"sensor_id": "eo-001", "sensor_type": "EO_CAMERA", "config": {"fov_deg": 90}},
    )
    assert response.status_code == 200


def test_get_sensors():
    client = TestClient(app)
    response = client.get("/sensors")
    assert response.status_code == 200
    payload = response.json()
    assert "sensors" in payload
    assert isinstance(payload["sensors"], list)
