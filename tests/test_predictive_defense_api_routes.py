"""Unit tests for predictive defense FastAPI routes."""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client() -> TestClient:
    api_routes = importlib.import_module("services.predictive_defense.api_routes")
    api_routes = importlib.reload(api_routes)
    app = FastAPI()
    app.include_router(api_routes.router)
    return TestClient(app)


def test_genome_context_updates_predictions_commands_alerts_and_posture() -> None:
    client = _build_client()

    seed = client.post(
        "/predictive-defense/genome-context",
        json={"track_id": "trk-901", "context": {"threat_score": 0.82, "predicted_intent": "attack"}},
    )
    assert seed.status_code == 200
    assert seed.json()["status"] == "context_set"

    predictions = client.get("/predictive-defense/predictions")
    assert predictions.status_code == 200
    payload = predictions.json()
    assert payload["count"] == 1
    assert payload["predictions"][0]["track_id"] == "trk-901"

    commands = client.get("/predictive-defense/commands")
    assert commands.status_code == 200
    assert commands.json()["count"] == 1

    alerts = client.get("/predictive-defense/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()["alerts"]) == 1

    posture = client.get("/predictive-defense/posture")
    assert posture.status_code == 200
    assert posture.json()["posture"] == "high"


def test_posture_defaults_when_no_alerts() -> None:
    client = _build_client()
    response = client.get("/predictive-defense/posture")
    assert response.status_code == 200
    assert response.json() == {"posture": "normal", "severity": "low"}


def test_genome_context_requires_track_id() -> None:
    client = _build_client()
    response = client.post("/predictive-defense/genome-context", json={"context": {"threat_score": 0.2}})
    assert response.status_code == 400
    assert "track_id required" in response.json()["detail"]


def test_genome_context_rejects_non_object_context() -> None:
    client = _build_client()
    response = client.post(
        "/predictive-defense/genome-context",
        json={"track_id": "trk-100", "context": ["not", "an", "object"]},
    )
    assert response.status_code == 400
    assert "context must be an object" in response.json()["detail"]


def test_alerts_query_validates_limit_bounds() -> None:
    client = _build_client()
    low = client.get("/predictive-defense/alerts?limit=0")
    high = client.get("/predictive-defense/alerts?limit=201")

    assert low.status_code == 422
    assert high.status_code == 422

