"""Unit tests for radar FastAPI routes."""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client() -> TestClient:
    api_routes = importlib.import_module("services.radar.api_routes")
    api_routes = importlib.reload(api_routes)
    app = FastAPI()
    app.include_router(api_routes.router)
    return TestClient(app)


def test_register_list_and_status_flow() -> None:
    client = _build_client()
    register = client.post(
        "/radar/radars/register",
        json={
            "name_en": "Sector Radar Alpha",
            "name_ar": "رادار القطاع ألف",
            "radar_type": "generic_3d",
            "band": "X",
            "position": [1000.0, 2000.0, 15.0],
            "max_range_m": 80000.0,
        },
    )
    assert register.status_code == 200
    radar_id = register.json()["radar_id"]

    listing = client.get("/radar/radars")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["count"] == 1
    assert payload["radars"][0]["radar_id"] == radar_id

    status = client.get(f"/radar/radars/{radar_id}/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["scans_received"] == 0
    assert status_payload["plots_received"] == 0
    assert status_payload["last_scan"] is None


def test_scan_ingest_and_fusion_confirm_track() -> None:
    client = _build_client()
    register = client.post("/radar/radars/register", json={})
    radar_id = register.json()["radar_id"]

    first_scan = client.post(
        f"/radar/radars/{radar_id}/scan",
        json={
            "plots": [
                {"position": [10.0, 20.0, 1000.0], "rcs_classification": "medium", "track_id": "trk-1"},
                {"position": [11.0, 21.0, 1002.0], "rcs_classification": "unknown"},
            ]
        },
    )
    assert first_scan.status_code == 200
    first_payload = first_scan.json()
    assert first_payload["plots_processed"] == 2
    assert first_payload["classified"] == 1
    assert first_payload["correlated"] == 1

    fusion_first = client.post("/radar/radars/fuse")
    assert fusion_first.status_code == 200
    assert fusion_first.json()["tracks"] == 1
    assert fusion_first.json()["confirmed"] == 0

    second_scan = client.post(
        f"/radar/radars/{radar_id}/scan",
        json={"plots": [{"position": [12.0, 22.0, 1004.0], "rcs_classification": "medium", "track_id": "trk-1"}]},
    )
    assert second_scan.status_code == 200

    fusion_second = client.post("/radar/radars/fuse")
    assert fusion_second.status_code == 200
    assert fusion_second.json()["confirmed"] >= 1


def test_register_validation_rejects_invalid_position() -> None:
    client = _build_client()
    response = client.post("/radar/radars/register", json={"position": [1.0, 2.0]})
    assert response.status_code == 400
    assert "position" in response.json()["detail"]


def test_setup_krechet_suite_and_stats() -> None:
    client = _build_client()
    setup = client.post("/radar/setup/krechet-suite", json={"center": [0.0, 0.0, 0.0]})
    assert setup.status_code == 200
    payload = setup.json()
    assert payload["radars_created"] == 4
    assert len(payload["radars"]) == 4
    assert payload["stats"]["radars_registered"] == 4


def test_setup_krechet_suite_rejects_invalid_center() -> None:
    client = _build_client()
    response = client.post("/radar/setup/krechet-suite", json={"center": [0.0, 0.0]})
    assert response.status_code == 400
    assert "center" in response.json()["detail"]


def test_tracks_endpoint_exposes_fused_air_picture() -> None:
    client = _build_client()
    register = client.post("/radar/radars/register", json={})
    radar_id = register.json()["radar_id"]

    first_scan = client.post(
        f"/radar/radars/{radar_id}/scan",
        json={"plots": [{"position": [10.0, 20.0, 1000.0], "rcs_classification": "small_uav", "track_id": "trk-radar"}]},
    )
    assert first_scan.status_code == 200
    client.post("/radar/radars/fuse")

    second_scan = client.post(
        f"/radar/radars/{radar_id}/scan",
        json={"plots": [{"position": [11.0, 20.0, 1002.0], "rcs_classification": "small_uav", "track_id": "trk-radar"}]},
    )
    assert second_scan.status_code == 200
    client.post("/radar/radars/fuse")

    tracks = client.get("/radar/tracks")
    assert tracks.status_code == 200
    payload = tracks.json()
    assert payload["count"] >= 1
    assert payload["confirmed"] >= 1
    fused_track = next(t for t in payload["tracks"] if t["track_id"] == "trk-radar")
    assert fused_track["classification"] == "ENEMY_UAV"

