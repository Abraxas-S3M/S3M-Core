"""API tests for Phase 13 cyber defense routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


def _sample_event() -> dict:
    return {
        "title": "SSH brute force detected",
        "description": "Repeated failed SSH logins from 203.0.113.10",
        "level": "HIGH",
        "category": "CYBER",
        "source": "MANUAL",
        "raw_data": {
            "src_ip": "203.0.113.10",
            "dest_ip": "10.0.0.15",
            "service": "ssh",
            "note": "brute force",
        },
        "confidence": 0.9,
    }


def _create_case(client: TestClient) -> str:
    response = client.post(
        "/cyber/cases",
        json={
            "title": "API Case",
            "description": "Created via API test",
            "severity": "HIGH",
            "source_events": ["evt-1"],
            "observables": [],
            "mitre_tactics": [],
            "mitre_techniques": [],
            "tags": ["api-test"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["case_id"]


def test_post_cyber_triage_200():
    client = TestClient(app)
    response = client.post("/cyber/triage", json={"event": _sample_event()})
    assert response.status_code == 200
    payload = response.json()
    assert "event_id" in payload
    assert "triage_score" in payload


def test_post_cyber_cases_200_with_case_id():
    client = TestClient(app)
    case_id = _create_case(client)
    assert isinstance(case_id, str)
    assert case_id


def test_get_cyber_cases_200_with_list():
    client = TestClient(app)
    _create_case(client)
    response = client.get("/cyber/cases")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_cyber_case_detail_200():
    client = TestClient(app)
    case_id = _create_case(client)
    response = client.get(f"/cyber/cases/{case_id}")
    assert response.status_code == 200
    assert response.json()["case_id"] == case_id


def test_patch_cyber_case_200():
    client = TestClient(app)
    case_id = _create_case(client)
    response = client.patch(
        f"/cyber/cases/{case_id}",
        json={"assigned_analyst": "analyst-api", "status": "IN_PROGRESS"},
    )
    assert response.status_code == 200
    assert response.json()["assigned_analyst"] == "analyst-api"


def test_get_cyber_playbooks_200_with_list():
    client = TestClient(app)
    response = client.get("/cyber/playbooks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_cyber_soc_overview_200_with_keys():
    client = TestClient(app)
    response = client.get("/cyber/soc/overview")
    assert response.status_code == 200
    payload = response.json()
    expected = {
        "open_cases",
        "cases_by_severity",
        "cases_by_status",
        "mean_resolution_hours",
        "alerts_last_hour",
        "playbooks_executed_today",
        "platforms_online",
        "mitre_heatmap",
        "top_observables",
        "analyst_workload",
    }
    assert expected.issubset(set(payload.keys()))


def test_get_cyber_mitre_heatmap_200():
    client = TestClient(app)
    response = client.get("/cyber/soc/mitre-heatmap")
    assert response.status_code == 200
    payload = response.json()
    assert "heatmap" in payload
    assert isinstance(payload["heatmap"], list)


def test_get_cyber_platform_status_200():
    client = TestClient(app)
    response = client.get("/cyber/platforms/status")
    assert response.status_code == 200
    payload = response.json()
    assert "thehive" in payload


def test_post_cyber_training_exercise_200():
    client = TestClient(app)
    response = client.post("/cyber/training/exercise", json={"scenario_type": "brute_force"})
    assert response.status_code == 200
    payload = response.json()
    assert "events_processed" in payload
