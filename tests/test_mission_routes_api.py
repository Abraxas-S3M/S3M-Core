#!/usr/bin/env python3
"""API tests for mission executive lifecycle routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.mission_routes import runtime
from src.api.server import app
from src.autonomy.mission_executive import MissionExecutive
from src.platforms.common.messages import Track


client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_mission_runtime() -> None:
    runtime.executive = MissionExecutive()
    runtime.reset_assignment()

    adapter = runtime.registry.get_platform("hmmwv-1")
    if adapter is not None and hasattr(adapter, "_position"):
        adapter._position = (0.0, 0.0, 0.0)
    runtime.registry.get_track_store()._tracks.clear()
    yield
    runtime.registry.get_track_store()._tracks.clear()


def test_start_status_and_phase_log() -> None:
    response = client.post(
        "/api/missions/start",
        json={
            "task_type": "patrol",
            "waypoints": [[150.0, 0.0, 0.0], [300.0, 0.0, 0.0]],
            "parameters": {"objective": "sector_sweep"},
            "assigned_platform": "hmmwv-1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["phase"] == "staging"
    assert payload["assigned_platform"] == "hmmwv-1"

    status = client.get("/api/missions/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["is_active"] is True
    assert status_payload["assigned_platform"] == "hmmwv-1"

    phase_log = client.get("/api/missions/phase-log")
    assert phase_log.status_code == 200
    log_payload = phase_log.json()
    assert log_payload["total"] >= 1
    assert any(entry["to_phase"] == "staging" for entry in log_payload["entries"])


def test_pause_resume_abort_lifecycle_routes() -> None:
    start = client.post(
        "/api/missions/start",
        json={
            "task_type": "patrol",
            "waypoints": [[120.0, 0.0, 0.0]],
            "parameters": {"priority": "high"},
            "assigned_platform": "hmmwv-1",
        },
    )
    assert start.status_code == 200

    pause = client.post("/api/missions/pause")
    assert pause.status_code == 200
    assert pause.json()["phase"] == "paused"

    resume = client.post("/api/missions/resume")
    assert resume.status_code == 200
    assert resume.json()["phase"] == "transit"

    abort = client.post("/api/missions/abort")
    assert abort.status_code == 200
    assert abort.json()["phase"] == "aborted"

    status = client.get("/api/missions/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["is_active"] is False
    assert status_payload["assigned_platform"] is None


def test_tick_reads_tracks_and_applies_mobility_command() -> None:
    start = client.post(
        "/api/missions/start",
        json={
            "task_type": "patrol",
            "waypoints": [[100.0, 0.0, 0.0]],
            "parameters": {"mode": "recon"},
            "assigned_platform": "hmmwv-1",
        },
    )
    assert start.status_code == 200

    runtime.registry.get_track_store().ingest_track(
        Track(track_id="trk-1", position=(25.0, 5.0, 0.0), confidence=0.9, classification="vehicle")
    )

    tick = client.post("/api/missions/tick")
    assert tick.status_code == 200
    payload = tick.json()
    assert payload["mobility_commands"]
    assert payload["sensor_commands"]
    assert payload["applied_commands"]
    assert payload["tracks"]

    adapter = runtime.registry.get_platform("hmmwv-1")
    assert adapter is not None
    state = adapter.read_state()
    assert state.position == (100.0, 0.0, 0.0)
