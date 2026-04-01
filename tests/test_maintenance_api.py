"""API tests for Phase 17 maintenance endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


client = TestClient(app)


def _register_asset() -> str:
    response = client.post(
        "/maintenance/assets",
        json={
            "name": "F-15SA",
            "designation": "F-15SA #API",
            "asset_type": "FIGHTER_JET",
            "serial_number": "F15-API-001",
            "manufacturer": "S3M Defense Industries",
            "model": "F-15SA",
            "location": "King Abdulaziz Air Base",
            "unit": "RSAF 3rd Wing",
            "hours": 3000.0,
        },
    )
    assert response.status_code == 200
    return response.json()["asset_id"]


def test_post_maintenance_assets_200_with_asset_id():
    asset_id = _register_asset()
    assert isinstance(asset_id, str)
    assert asset_id


def test_get_maintenance_assets_200():
    response = client.get("/maintenance/assets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_maintenance_assets_template_saudi_200_with_20_assets():
    response = client.post("/maintenance/assets/template/saudi")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 20
    assert len(payload["assets"]) == 20


def test_post_maintenance_telemetry_200():
    asset_id = _register_asset()
    response = client.post(
        "/maintenance/telemetry",
        json={
            "asset_id": asset_id,
            "readings": {"temperature_c": 460.0, "vibration_g": 3.8, "pressure_psi": 28.0},
            "operating_mode": "cruise",
        },
    )
    assert response.status_code == 200
    assert response.json()["asset_id"] == asset_id


def test_post_maintenance_predict_asset_200_with_rul():
    asset_id = _register_asset()
    for _ in range(12):
        client.post(
            "/maintenance/telemetry",
            json={
                "asset_id": asset_id,
                "readings": {
                    "temperature_c": 470.0,
                    "vibration_g": 4.0,
                    "pressure_psi": 27.0,
                    "oil_temp_c": 112.0,
                    "rpm": 12500,
                },
                "operating_mode": "combat",
            },
        )

    response = client.post(f"/maintenance/predict/{asset_id}")
    assert response.status_code == 200
    assert "rul_hours" in response.json()


def test_post_maintenance_work_orders_generate_200():
    response = client.post("/maintenance/work-orders/generate")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_maintenance_work_orders_200():
    response = client.get("/maintenance/work-orders")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_maintenance_procurement_check_200():
    response = client.post("/maintenance/procurement/check")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_maintenance_parts_200():
    response = client.get("/maintenance/parts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_maintenance_fleet_health_200():
    response = client.get("/maintenance/fleet/health")
    assert response.status_code == 200
    payload = response.json()
    assert "total_assets" in payload
    assert "readiness_score" in payload


def test_get_maintenance_fleet_readiness_200():
    response = client.get("/maintenance/fleet/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert "readiness_pct" in payload


def test_get_maintenance_status_200():
    response = client.get("/maintenance/status")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
