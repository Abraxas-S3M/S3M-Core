"""API tests for tactical platform adapter integration routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.platform_routes import platform_registry
from src.api.server import app


def test_platform_registry_bootstrap_contains_expected_ids() -> None:
    expected = {
        "hmmwv-001",
        "warwar-001",
        "g24-001",
        "horizon-001",
        "rcws127-001",
        "sich-001",
        "orion-001",
        "manpads-001",
    }
    for platform_id in expected:
        assert platform_registry.get(platform_id) is not None


def test_platform_connect_state_health_disconnect_for_ugv() -> None:
    client = TestClient(app)
    platform_id = "hmmwv-001"

    connect = client.post(f"/api/platforms/{platform_id}/connect")
    assert connect.status_code == 200
    assert connect.json()["success"] is True

    state = client.get(f"/api/platforms/{platform_id}/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["state_type"] == "platform"
    assert payload["platform_state"]["platform_id"] == platform_id

    health = client.get(f"/api/platforms/{platform_id}/health")
    assert health.status_code == 200
    assert health.json()["adapter_class"] == "HMMWVAdapter"

    disconnect = client.post(f"/api/platforms/{platform_id}/disconnect")
    assert disconnect.status_code == 200
    assert "success" in disconnect.json()


def test_payload_capabilities_and_state_surface_payload_metadata() -> None:
    client = TestClient(app)
    platform_id = "rcws127-001"

    _ = client.post(f"/api/platforms/{platform_id}/connect")
    state = client.get(f"/api/platforms/{platform_id}/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["state_type"] == "payload"
    assert payload["payload_state"]["payload_id"] == platform_id

    capabilities = client.get(f"/api/platforms/{platform_id}/capabilities")
    assert capabilities.status_code == 200
    caps_payload = capabilities.json()
    assert caps_payload["domain"] == "payload"
    assert "safe-state" in caps_payload["supported_operations"]


def test_platform_mobility_sensor_and_safe_state_routes_accept_commands() -> None:
    client = TestClient(app)
    platform_id = "hmmwv-001"

    mobility = client.post(
        f"/api/platforms/{platform_id}/mobility",
        json={"command_type": "move_to", "target_position": [10.0, 2.0, 0.0]},
    )
    assert mobility.status_code == 200
    assert "accepted" in mobility.json()

    sensor = client.post(
        f"/api/platforms/{platform_id}/sensor",
        json={"sensor": "camera_day", "enabled": False, "parameters": {"refresh_hz": 0}},
    )
    assert sensor.status_code == 200
    assert "accepted" in sensor.json()

    safe_state = client.post(
        f"/api/platforms/{platform_id}/safe-state",
        json={"reason": "operator_override"},
    )
    assert safe_state.status_code == 200
    assert safe_state.json()["accepted"] is True


def test_unknown_platform_returns_404() -> None:
    client = TestClient(app)
    response = client.get("/api/platforms/does-not-exist/state")
    assert response.status_code == 404
