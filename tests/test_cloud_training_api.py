from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import cloud_training_routes
from src.training.cloud_cpu.metrics_store import MetricsStore
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack


def _write_jsonl(path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


@pytest.fixture
def training_client(tmp_path, monkeypatch):
    paths = StatePaths(root=tmp_path / "state")
    metrics = MetricsStore(paths.metrics)

    monkeypatch.setattr(cloud_training_routes, "_paths", paths)
    monkeypatch.setattr(cloud_training_routes, "_metrics", metrics)

    app = FastAPI()
    app.include_router(cloud_training_routes.cloud_training_router)
    return TestClient(app), paths


def test_status_and_metrics_endpoints(training_client) -> None:
    client, paths = training_client
    _write_jsonl(
        paths.metrics / "saudi_mod.jsonl",
        [{"cycle": 1, "loss": 0.8, "timestamp": "2026-01-01T00:00:00Z"}],
    )

    status_resp = client.get("/api/v1/training/status")
    assert status_resp.status_code == 200
    assert "saudi_mod" in status_resp.json()["tracks"]

    metrics_resp = client.get("/api/v1/training/metrics", params={"track": "saudi_mod", "n": 1})
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["metrics"][0]["cycle"] == 1


def test_pause_resume_and_invalid_track(training_client) -> None:
    client, paths = training_client

    pause_resp = client.post("/api/v1/training/pause", params={"track": "nato"})
    assert pause_resp.status_code == 200
    assert (paths.locks / "nato.pause").exists()

    resume_resp = client.post("/api/v1/training/resume", params={"track": "nato"})
    assert resume_resp.status_code == 200
    assert not (paths.locks / "nato.pause").exists()

    bad_resp = client.get("/api/v1/training/metrics", params={"track": "unknown", "n": 1})
    assert bad_resp.status_code == 400


def test_checkpoints_promote_tracks_and_kpis(training_client) -> None:
    client, paths = training_client
    track_paths = paths.for_track(TrainingTrack.SAUDI_MOD)

    run_ckpt = track_paths.runs / "ckpt-001"
    run_ckpt.mkdir(parents=True, exist_ok=True)
    (run_ckpt / "manifest.json").write_text(
        json.dumps({"checkpoint": "ckpt-001", "cycle": 5}),
        encoding="utf-8",
    )
    (run_ckpt / "weights.q4").write_text("edge-quantized", encoding="utf-8")
    _write_jsonl(
        paths.metrics / "saudi_mod.jsonl",
        [{"cycle": 5, "accuracy": 0.77, "timestamp": "2026-01-01T02:00:00Z"}],
    )

    promote_resp = client.post(
        "/api/v1/training/promote",
        params={"track": "saudi_mod", "checkpoint": "ckpt-001"},
    )
    assert promote_resp.status_code == 200
    assert (track_paths.promoted / "ckpt-001" / "manifest.json").exists()

    list_resp = client.get("/api/v1/training/checkpoints", params={"track": "saudi_mod"})
    assert list_resp.status_code == 200
    assert list_resp.json()["latest_promoted"]["checkpoint"] == "ckpt-001"

    tracks_resp = client.get("/api/v1/training/tracks")
    assert tracks_resp.status_code == 200
    assert "summary" in tracks_resp.json()["tracks"]["saudi_mod"]

    kpis_resp = client.get("/api/v1/training/kpis", params={"track": "saudi_mod"})
    assert kpis_resp.status_code == 200
    assert kpis_resp.json()["track"] == "saudi_mod"
