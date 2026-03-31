#!/usr/bin/env python3
"""API tests for Layer 04 simulation and wargaming routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


def test_get_simulation_status():
    client = TestClient(app)
    resp = client.get("/simulation/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert "status" in payload
    assert "adapters" in payload


def test_get_adapters():
    client = TestClient(app)
    resp = client.get("/simulation/adapters")
    assert resp.status_code == 200
    payload = resp.json()
    assert "adapters" in payload
    adapter_names = {entry["name"] for entry in payload["adapters"]}
    assert "builtin" in adapter_names


def test_connect_builtin_adapter():
    client = TestClient(app)
    resp = client.post(
        "/simulation/adapters/builtin/connect",
        json={"simulator_name": "builtin", "host": "localhost", "port": 0, "headless": True, "extra_params": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["connected"] is True


def test_list_scenarios():
    client = TestClient(app)
    resp = client.get("/simulation/scenarios")
    assert resp.status_code == 200
    payload = resp.json()
    assert "scenarios" in payload
    assert isinstance(payload["scenarios"], list)


def test_generate_network_synthetic_data():
    client = TestClient(app)
    resp = client.post(
        "/simulation/synthetic/generate",
        json={"data_type": "network", "n_records": 250, "params": {"attack_ratio": 0.2}},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["record_count"] == 250


def test_list_synthetic_datasets():
    client = TestClient(app)
    client.post(
        "/simulation/synthetic/generate",
        json={"data_type": "sensor", "n_records": 120, "params": {"n_sensors": 4, "anomaly_ratio": 0.1}},
    )
    resp = client.get("/simulation/synthetic/datasets")
    assert resp.status_code == 200
    payload = resp.json()
    assert "datasets" in payload
    assert isinstance(payload["datasets"], list)


def test_list_replays():
    client = TestClient(app)
    resp = client.get("/simulation/replays")
    assert resp.status_code == 200
    payload = resp.json()
    assert "replays" in payload
    assert isinstance(payload["replays"], list)
