"""Unit tests for standalone edge server bootstrap behavior."""

from __future__ import annotations

import json
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.edge_compute import edge_server


def test_edge_server_root_endpoint() -> None:
    client = TestClient(edge_server.app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "S3M Edge Node"
    assert payload["status"] == "online"


def test_edge_server_config_loader(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "params.json"
    cfg_path.write_text(json.dumps({"container_runtime": "docker", "scheduling_policy": "adaptive"}), encoding="utf-8")
    monkeypatch.setenv("S3M_CONFIG_PATH", str(cfg_path))
    loaded = edge_server._load_config()
    assert loaded["container_runtime"] == "docker"
    assert loaded["scheduling_policy"] == "adaptive"
