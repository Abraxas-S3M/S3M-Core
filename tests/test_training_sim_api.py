from fastapi.testclient import TestClient

from src.api.server import app


client = TestClient(app)


def test_post_training_wargame():
    resp = client.post(
        "/training/wargame",
        json={
            "name": "API WG",
            "type": "tactical",
            "blue_units_or_force_id": 3,
            "red_units_or_force_id": 3,
            "turns": 3,
            "adversary_difficulty": "competent",
            "llm_adversary": True,
        },
    )
    assert resp.status_code == 200
    assert "session_id" in resp.json()


def test_post_training_wargame_quick():
    resp = client.post(
        "/training/wargame/quick",
        json={"name": "Quick", "blue_units": 3, "red_units": 3, "turns": 3, "adversary": "competent"},
    )
    assert resp.status_code == 200
    assert "result" in resp.json()


def test_post_orders():
    create = client.post(
        "/training/wargame",
        json={
            "name": "API WG2",
            "type": "tactical",
            "blue_units_or_force_id": 2,
            "red_units_or_force_id": 2,
            "turns": 3,
            "adversary_difficulty": "competent",
            "llm_adversary": True,
        },
    ).json()
    session_id = create["session_id"]
    resp = client.post(
        f"/training/wargame/{session_id}/orders",
        json={"session_id": session_id, "orders": [{"unit_id": "blue-1", "action": "move", "target": [10, 0]}]},
    )
    assert resp.status_code == 200


def test_post_exercises_tabletop():
    resp = client.post("/training/exercises/tabletop", json={"name": "TTX", "brief": "Brief", "participants": []})
    assert resp.status_code == 200


def test_post_officer_and_get_profile():
    reg = client.post("/training/officers", json={"name": "Officer", "rank": "Captain", "unit": "U", "specialization": "infantry"})
    assert reg.status_code == 200
    oid = reg.json()["officer"]["officer_id"]
    profile = client.get(f"/training/officers/{oid}")
    assert profile.status_code == 200


def test_post_scenario_from_brief():
    resp = client.post("/training/scenarios/from-brief", json={"brief": "Defend sector"})
    assert resp.status_code == 200


def test_get_courses_and_generate_standard():
    gen = client.post("/training/courses/standard")
    assert gen.status_code == 200
    assert len(gen.json()["courses"]) == 5
    resp = client.get("/training/courses")
    assert resp.status_code == 200


def test_get_portal_overview_leaderboard_status():
    assert client.get("/training/portal/overview").status_code == 200
    assert client.get("/training/leaderboard").status_code == 200
    assert client.get("/training/status").status_code == 200
