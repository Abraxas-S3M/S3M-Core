from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.cop.cop_routes import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_cop_state_returns_saudi_mod_payload() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/cop/saudi_mod/state")
    assert response.status_code == 200
    payload = response.json()

    assert payload["track"] == "saudi_mod"
    assert payload["theater"]["center"] == [24.7136, 46.6753]
    assert payload["theater"]["bounds"] == [[15.5, 34.0], [32.8, 56.8]]
    assert isinstance(payload["tactical_tracks"], list)
    assert isinstance(payload["alerts"], list)
    assert isinstance(payload["panel_summaries"], list)
    assert "timestamp" in payload


def test_cop_track_validation_rejects_unsupported_track() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/cop/unknown/state")
    assert response.status_code == 404
    assert "Unsupported COP track" in response.json()["detail"]


def test_cop_map_endpoint_includes_features_and_map_config() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/cop/saudi_mod/map")
    assert response.status_code == 200
    payload = response.json()

    assert payload["track"] == "saudi_mod"
    assert "map_config" in payload
    assert "geospatial_features" in payload
    assert isinstance(payload["geospatial_features"], list)


@pytest.mark.parametrize(
    ("endpoint", "key"),
    [
        ("/api/cop/saudi_mod/tracks", "tracks"),
        ("/api/cop/saudi_mod/alerts", "alerts"),
        ("/api/cop/saudi_mod/decisions", "decisions"),
        ("/api/cop/saudi_mod/feed", "feed"),
    ],
)
def test_cop_collection_endpoints_return_dashboard_ready_lists(endpoint: str, key: str) -> None:
    client = TestClient(_build_app())

    response = client.get(endpoint)
    assert response.status_code == 200
    payload = response.json()

    assert payload["track"] == "saudi_mod"
    assert key in payload
    assert isinstance(payload[key], list)
    assert "timestamp" in payload


def test_cop_websocket_sends_initial_state() -> None:
    client = TestClient(_build_app())

    with client.websocket_connect("/ws/cop/saudi_mod") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "cop_update"
        assert message["state"]["track"] == "saudi_mod"
