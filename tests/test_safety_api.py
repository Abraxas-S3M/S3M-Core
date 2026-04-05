"""API tests for safety control authority route integration."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def _register_operator(authority_level: str) -> str:
    operator_id = f"op-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/safety/operators",
        json={"operator_id": operator_id, "authority_level": authority_level},
    )
    assert response.status_code == 200
    return operator_id


def _issue_auth(operator_id: str, auth_type: str = "engage") -> str:
    response = client.post(
        "/api/safety/authorize",
        json={"operator_id": operator_id, "auth_type": auth_type, "ttl_seconds": 600},
    )
    assert response.status_code == 200
    return response.json()["auth_id"]


def test_safety_authorization_lifecycle():
    operator_id = _register_operator("operator")
    auth_id = _issue_auth(operator_id, auth_type="engage")

    validate_response = client.get(f"/api/safety/authorize/{auth_id}/validate")
    assert validate_response.status_code == 200
    assert validate_response.json()["valid"] is True

    revoke_response = client.post(f"/api/safety/authorize/{auth_id}/revoke")
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked"] is True

    validate_after_revoke = client.get(f"/api/safety/authorize/{auth_id}/validate")
    assert validate_after_revoke.status_code == 200
    assert validate_after_revoke.json()["valid"] is False


def test_safety_interlock_state_and_emergency_stop():
    operator_id = _register_operator("operator")
    auth_id = _issue_auth(operator_id, auth_type="engage")
    payload_id = f"payload-{uuid.uuid4().hex[:8]}"

    initial_state = client.get(f"/api/safety/interlocks/{payload_id}")
    assert initial_state.status_code == 200
    assert initial_state.json()["state"] == "safe"

    arm_response = client.post(
        f"/api/safety/interlocks/{payload_id}/transition",
        json={"requested_state": "armed", "auth_id": auth_id},
    )
    assert arm_response.status_code == 200
    assert arm_response.json()["state"] == "armed"

    fire_response = client.post(
        f"/api/safety/interlocks/{payload_id}/transition",
        json={"requested_state": "firing", "auth_id": auth_id},
    )
    assert fire_response.status_code == 200
    assert fire_response.json()["state"] == "firing"

    stop_response = client.post("/api/safety/emergency-stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["payload_states"][payload_id] == "safe"


def test_safety_sim_mode_requires_mission_commander():
    team_lead_id = _register_operator("team_lead")
    team_lead_auth = _issue_auth(team_lead_id, auth_type="mobility")
    denied = client.post(
        "/api/safety/sim-mode",
        json={
            "simulation_mode": True,
            "reason": "exercise",
            "auth_id": team_lead_auth,
        },
    )
    assert denied.status_code == 403

    mission_commander_id = _register_operator("mission_commander")
    mission_commander_auth = _issue_auth(mission_commander_id, auth_type="mobility")
    allowed = client.post(
        "/api/safety/sim-mode",
        json={
            "simulation_mode": True,
            "reason": "training window",
            "auth_id": mission_commander_auth,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["simulation_mode"] is True

    mode = client.get("/api/safety/sim-mode")
    assert mode.status_code == 200
    assert mode.json()["simulation_mode"] is True


def test_safety_geofence_and_range_violations():
    geofence_response = client.post(
        "/api/safety/geofence",
        json={
            "geofence_id": f"gf-{uuid.uuid4().hex[:8]}",
            "polygon": [
                {"x": 10.0, "y": 10.0},
                {"x": 10.0, "y": 20.0},
                {"x": 20.0, "y": 20.0},
                {"x": 20.0, "y": 10.0},
            ],
            "policy": "forbidden",
        },
    )
    assert geofence_response.status_code == 200

    baseline = client.get("/api/safety/range-violations")
    assert baseline.status_code == 200
    baseline_count = baseline.json()["total"]

    check = client.get(
        "/api/safety/range-violations",
        params={"platform_id": f"plat-{uuid.uuid4().hex[:8]}", "x": 12.0, "y": 12.0, "z": 50.0},
    )
    assert check.status_code == 200
    assert check.json()["total"] >= baseline_count + 1


def test_safety_audit_log_endpoint():
    response = client.get("/api/safety/audit-log")
    assert response.status_code == 200
    payload = response.json()
    assert "entries" in payload
    assert "total" in payload
