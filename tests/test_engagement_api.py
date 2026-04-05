#!/usr/bin/env python3
"""API tests for engagement evaluation and authorization routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.engagement_routes import runtime
from src.api.server import app
from src.platforms.common import ROEProfile


client = TestClient(app)


def _reset_runtime_state() -> None:
    runtime.recommendations.clear()
    runtime.engagement_log.clear()
    runtime.blue_force_positions.clear()
    runtime.roe_profiles = {"default": ROEProfile.WEAPONS_TIGHT}
    runtime.active_roe_profile_id = "default"
    # Test-only reset: clear TrackStore state to keep tactical evaluations deterministic.
    runtime.track_store._tracks.clear()  # noqa: SLF001


def test_engagement_evaluate_and_authorize_hool_flow() -> None:
    _reset_runtime_state()

    update_blue_force = client.post(
        "/api/engagement/blue-force",
        json={
            "positions": [
                {
                    "unit_id": "blue-1",
                    "position": [0.0, 0.0, 0.0],
                }
            ]
        },
    )
    assert update_blue_force.status_code == 200
    assert update_blue_force.json()["updated"] == 1

    evaluate = client.post(
        "/api/engagement/evaluate",
        json={
            "roe_profile_id": "default",
            "ingest_tracks": [
                {
                    "track_id": "hostile-1",
                    "position": [100.0, 25.0, 0.0],
                    "confidence": 0.95,
                    "classification": "hostile",
                    "threat_priority": "critical",
                }
            ],
        },
    )
    assert evaluate.status_code == 200
    recommendations = evaluate.json()
    assert len(recommendations) == 1
    recommendation_id = recommendations[0]["recommendation_id"]
    assert recommendations[0]["roe_compliant"] is True
    assert recommendations[0]["recommended_effector"] is not None

    hool = client.post(
        "/api/engagement/authorize-hool",
        json={
            "recommendation_id": recommendation_id,
            "active_mission_token": True,
            "allow_auto_engagement": True,
            "operator_id": "autonomy-supervisor",
        },
    )
    assert hool.status_code == 200
    payload = hool.json()
    assert payload["authorized"] is True
    assert payload["action"] == "engage"


def test_engagement_roe_upsert_hotl_and_log() -> None:
    _reset_runtime_state()

    upsert = client.post(
        "/api/engagement/roe",
        json={
            "profile_id": "strict",
            "roe_profile": "weapons_hold",
            "set_active": True,
        },
    )
    assert upsert.status_code == 200
    assert upsert.json()["active_profile_id"] == "strict"

    list_roe = client.get("/api/engagement/roe")
    assert list_roe.status_code == 200
    profiles = list_roe.json()["profiles"]
    assert any(profile["profile_id"] == "strict" for profile in profiles)

    evaluate = client.post(
        "/api/engagement/evaluate",
        json={
            "roe_profile_id": "strict",
            "ingest_tracks": [
                {
                    "track_id": "hostile-2",
                    "position": [300.0, 0.0, 0.0],
                    "confidence": 0.91,
                    "classification": "hostile",
                    "threat_priority": "high",
                }
            ],
        },
    )
    assert evaluate.status_code == 200
    recommendation_id = evaluate.json()[0]["recommendation_id"]

    hotl = client.post(
        "/api/engagement/authorize-hotl",
        json={
            "recommendation_id": recommendation_id,
            "operator_id": "operator-1",
            "authorize": False,
            "rationale": "manual veto",
        },
    )
    assert hotl.status_code == 200
    assert hotl.json()["authorized"] is False
    assert hotl.json()["action"] == "hold_fire"

    logs = client.get("/api/engagement/log", params={"limit": 20})
    assert logs.status_code == 200
    body = logs.json()
    assert body["total"] >= 3
    assert len(body["entries"]) >= 1

