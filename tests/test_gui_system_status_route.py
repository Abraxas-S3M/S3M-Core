from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.gui_bridge import gui_bridge_router


def test_system_status_shape() -> None:
    app = FastAPI()
    app.include_router(gui_bridge_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/system/status")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "operational"
    assert isinstance(data["engines"], dict)
    assert isinstance(data["uptime"], int)
    assert data["uptime"] >= 0
    assert data["version"] == "0.2.0"
    datetime.fromisoformat(data["updatedAt"])
