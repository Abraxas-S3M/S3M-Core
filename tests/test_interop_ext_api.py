"""API tests for Phase 16 extended interoperability routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


def test_post_interop_exercises_200_with_exercise_id():
    client = TestClient(app)
    resp = client.post(
        "/interop/exercises",
        json={
            "name": "API Exercise",
            "description": "Interop API test",
            "nations": [{"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["exercise_id"] >= 1


def test_get_interop_exercises_200():
    client = TestClient(app)
    client.post(
        "/interop/exercises",
        json={
            "name": "API Exercise 2",
            "description": "Interop API test list",
            "nations": [{"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"}],
        },
    )
    resp = client.get("/interop/exercises")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_interop_orbat_forces_200():
    client = TestClient(app)
    resp = client.post("/interop/orbat/forces", json={"name": "Force A", "affiliation": "friendly"})
    assert resp.status_code == 200
    assert "force_id" in resp.json()


def test_post_interop_orbat_template_saudi_200_complete():
    client = TestClient(app)
    resp = client.post("/interop/orbat/template/saudi")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["country_code"] == 178
    assert len(payload["units"]) >= 12


def test_get_interop_orbat_forces_200():
    client = TestClient(app)
    client.post("/interop/orbat/template/saudi")
    resp = client.get("/interop/orbat/forces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_interop_msdl_export_200_with_xml():
    client = TestClient(app)
    client.post("/interop/orbat/template/saudi")
    resp = client.post("/interop/msdl/export")
    assert resp.status_code == 200
    assert "<MilitaryScenario" in resp.json()["xml"]


def test_post_interop_verify_200_with_results():
    client = TestClient(app)
    resp = client.post("/interop/verify")
    assert resp.status_code == 200
    payload = resp.json()
    assert "summary" in payload
    assert "dis" in payload


def test_get_interop_partners_200_with_gcc_codes():
    client = TestClient(app)
    resp = client.get("/interop/partners")
    assert resp.status_code == 200
    gcc = resp.json()["gcc"]
    assert gcc["Saudi Arabia"] == 178
    assert len(gcc) == 6


def test_get_interop_status_200():
    client = TestClient(app)
    resp = client.get("/interop/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert "exercise_manager" in payload
    assert "registry" in payload
