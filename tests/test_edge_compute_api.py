"""Integration tests for edge compute API and dashboard mounts."""

from __future__ import annotations

import os
import sys
from typing import Dict

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import app
from src.edge_compute.api import set_manager


def _client() -> TestClient:
    return TestClient(app)


def setup_function() -> None:
    # Ensure tests do not leak manager state across cases.
    set_manager(None)


def test_edge_health_endpoint_available() -> None:
    client = _client()
    response = client.get("/edge/health")
    assert response.status_code == 200
    payload = response.json()
    assert "federated" in payload
    assert "heterogeneous_compute" in payload


def test_edge_federated_node_lifecycle() -> None:
    client = _client()
    register = client.post(
        "/edge/federated/nodes",
        json={
            "node_id": "node-alpha",
            "hostname": "alpha",
            "memory_mb": 2048,
            "cpu_cores": 4,
            "gpu_available": False,
        },
    )
    assert register.status_code == 200

    listed = client.get("/edge/federated/nodes")
    assert listed.status_code == 200
    nodes = listed.json()["nodes"]
    assert any(item["node_id"] == "node-alpha" for item in nodes)

    deleted = client.delete("/edge/federated/nodes/node-alpha")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deregistered"


def test_edge_bootstrap_requires_global_model_first() -> None:
    client = _client()
    response = client.post(
        "/edge/bootstrap",
        json={"parent_node_id": "parent-1", "target_memory_mb": 2048, "deploy_sandbox": False},
    )
    assert response.status_code == 400
    assert "No global model initialized" in response.json()["detail"]


def test_edge_bootstrap_success_after_global_init() -> None:
    client = _client()
    init = client.post("/edge/federated/global-model/init", json={"input_dim": 4, "output_dim": 2})
    assert init.status_code == 200

    response = client.post(
        "/edge/bootstrap",
        json={"parent_node_id": "parent-1", "target_memory_mb": 2048, "deploy_sandbox": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "replica" in payload
    assert "node_info" in payload
    assert payload["sandbox"] is not None


def test_edge_compute_execute_matmul() -> None:
    client = _client()
    response = client.post(
        "/edge/compute/execute",
        json={
            "operation": "matmul",
            "left": [[1.0, 2.0], [3.0, 4.0]],
            "right": [[1.0, 0.0], [0.0, 1.0]],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["device"] in {"cpu", "gpu"}
    assert payload["result"] == [[1.0, 2.0], [3.0, 4.0]]


def test_edge_sandbox_deploy_and_param_update() -> None:
    client = _client()
    deployed = client.post(
        "/edge/sandbox/deploy",
        json={"cpu_cores": 2, "memory_mb": 1024, "gpu_passthrough": False, "params": {"temperature": 0.6}},
    )
    assert deployed.status_code == 200
    sandbox_id = deployed.json()["sandbox_id"]

    updated = client.post(
        f"/edge/sandbox/{sandbox_id}/params",
        json={"updates": {"training_enabled": True}},
    )
    assert updated.status_code == 200
    assert updated.json()["params"]["training_enabled"] is True

    params = client.get(f"/edge/sandbox/{sandbox_id}/params")
    assert params.status_code == 200
    assert params.json()["training_enabled"] is True


def test_dashboard_edge_endpoints_available() -> None:
    client = _client()
    paths = [
        "/dashboard/edge",
        "/dashboard/edge/network",
        "/dashboard/edge/training",
        "/dashboard/edge/replicas",
        "/dashboard/edge/data",
        "/dashboard/edge/sandboxes",
        "/dashboard/edge/compute",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} unavailable"
