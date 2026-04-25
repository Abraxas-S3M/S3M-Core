from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.demo.demo_room_service import VALID_TRACKS, demo_room, demo_ws_endpoint, router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.add_api_websocket_route("/ws/demo-room", demo_ws_endpoint)
    return app


def test_fallback_scenario_contains_required_events() -> None:
    events = demo_room._fallback_scenario("saudi_mod")
    assert len(events) == 11
    assert [event.sequence for event in events] == list(range(1, 12))
    assert all(event.total == 11 for event in events)

    expected_event_types = [
        "system",
        "engine_status",
        "engine_status",
        "engine_status",
        "engine_status",
        "intel_feed",
        "cop_update",
        "risk_card",
        "artifact",
        "assessment",
        "alert",
    ]
    assert [event.event_type for event in events] == expected_event_types
    assert [event.engine for event in events[1:5]] == ["phi3", "mixtral", "allam", "grok"]
    assert "arabic" in events[8].body


def test_tracks_endpoint_lists_all_supported_tracks() -> None:
    app = _build_app()
    client = TestClient(app)

    response = client.get("/api/demo/tracks")
    assert response.status_code == 200
    payload = response.json()
    returned_tracks = {item["name"] for item in payload["tracks"]}
    assert returned_tracks == set(VALID_TRACKS)


def test_launch_endpoint_rejects_invalid_track() -> None:
    app = _build_app()
    client = TestClient(app)

    response = client.post(
        "/api/demo/launch",
        json={"track": "invalid_track", "scenario": "default", "pacing": "fast"},
    )
    assert response.status_code == 400
    assert "Invalid track" in response.json()["detail"]


def test_websocket_status_and_stop_commands(monkeypatch) -> None:
    app = _build_app()
    client = TestClient(app)

    status_payload = {
        "session_id": "session-123",
        "track": "nato",
        "phase": "idle",
        "scenario": "default",
        "pacing": "fast",
        "connected_clients": 0,
        "event_count": 0,
    }
    stop_payload = {
        **status_payload,
        "phase": "stopped",
    }

    async def fake_stop():
        return stop_payload

    monkeypatch.setattr(demo_room, "get_status", lambda: status_payload)
    monkeypatch.setattr(demo_room, "stop", fake_stop)

    with client.websocket_connect("/ws/demo-room") as websocket:
        connected_status = websocket.receive_json()
        assert connected_status["type"] == "status"
        assert connected_status["status"] == status_payload

        websocket.send_json({"command": "status"})
        status_response = websocket.receive_json()
        assert status_response["type"] == "status"
        assert status_response["status"] == status_payload

        websocket.send_json({"command": "stop"})
        stop_response = websocket.receive_json()
        assert stop_response["type"] == "status"
        assert stop_response["status"] == stop_payload
