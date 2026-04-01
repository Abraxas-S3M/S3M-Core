"""API tests for S3M Phase 20 readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


client = TestClient(app)


def _register_member() -> str:
    service_number = f"API-{len(client.get('/readiness/personnel').json())+1:04d}"
    response = client.post(
        "/readiness/personnel",
        json={
            "name_en": "Fahad Al-Harbi",
            "name_ar": "فهد الحربي",
            "rank": "CAPTAIN",
            "branch": "ARMY",
            "mos": "11A",
            "mos_desc_en": "Armor Officer",
            "mos_desc_ar": "ضابط مدرعات",
            "unit_id": "unit-api",
            "unit_name_en": "API Unit",
            "unit_name_ar": "وحدة API",
            "service_number": service_number,
            "clearance": "SECRET",
            "medical": "FIT_FOR_DUTY",
            "languages": ["ar", "en"],
            "specializations": ["armor_crewman"],
        },
    )
    assert response.status_code == 200
    return response.json()["member_id"]


def test_post_readiness_personnel_200_with_member_id():
    member_id = _register_member()
    assert isinstance(member_id, str)
    assert member_id


def test_get_readiness_personnel_200():
    response = client.get("/readiness/personnel")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_readiness_personnel_template_battalion_200_with_45():
    response = client.post("/readiness/personnel/template/battalion")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 45


def test_post_readiness_certifications_200():
    member_id = _register_member()
    response = client.post(
        "/readiness/certifications",
        json={
            "member_id": member_id,
            "type": "S3M_WARGAMING_L1",
            "name_en": "Wargaming Operator Level 1",
            "name_ar": "مشغل ألعاب حربية مستوى 1",
            "authority": "S3M Training Center",
            "score": 92.0,
            "expiry_days": 365,
            "course_id": "C-101",
        },
    )
    assert response.status_code == 200
    assert response.json()["member_id"] == member_id


def test_get_readiness_certifications_expiring_200():
    response = client.get("/readiness/certifications/expiring")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_readiness_units_200():
    response = client.post(
        "/readiness/units",
        json={"name_en": "API Unit", "name_ar": "وحدة API", "authorized_strength": 20, "orbat_unit_id": None},
    )
    assert response.status_code == 200
    assert "unit_id" in response.json()


def test_post_readiness_units_autofill_200():
    member_id = _register_member()
    unit = client.post(
        "/readiness/units",
        json={"name_en": "AutoFill Unit", "name_ar": "وحدة تعبئة", "authorized_strength": 1, "orbat_unit_id": None},
    ).json()
    client.post(
        f"/readiness/units/{unit['unit_id']}/slots",
        json={
            "position_title_en": "Signals Officer",
            "position_title_ar": "ضابط إشارات",
            "required_rank": "CAPTAIN",
            "required_mos": "11A",
            "required_clearance": "CONFIDENTIAL",
            "required_certs": [],
        },
    )
    client.patch(
        f"/readiness/personnel/{member_id}/status",
        json={"member_id": member_id, "status": "ACTIVE_DUTY"},
    )
    response = client.post(f"/readiness/units/{unit['unit_id']}/auto-fill")
    assert response.status_code == 200
    assert "filled" in response.json()


def test_get_readiness_units_vacancies_200():
    response = client.get("/readiness/units/vacancies")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_post_readiness_eligibility_200():
    member_id = _register_member()
    response = client.post(f"/readiness/eligibility/{member_id}")
    assert response.status_code == 200
    assert "eligible" in response.json()


def test_post_readiness_score_unit_200():
    unit = client.post(
        "/readiness/units",
        json={"name_en": "Score Unit", "name_ar": "وحدة التقييم", "authorized_strength": 5, "orbat_unit_id": None},
    ).json()
    response = client.post(f"/readiness/score/{unit['unit_id']}")
    assert response.status_code == 200
    assert "overall_readiness" in response.json()


def test_get_readiness_overview_200_with_keys():
    response = client.get("/readiness/overview")
    assert response.status_code == 200
    payload = response.json()
    for key in [
        "total_personnel",
        "deployable",
        "deployable_pct",
        "by_branch",
        "by_rank_group",
        "by_status",
        "units",
        "expiring_certs_30d",
        "expired_certs",
        "critical_vacancies",
        "overall_readiness",
        "readiness_level",
        "coalition_partners",
    ]:
        assert key in payload


def test_get_readiness_manning_board_200():
    response = client.get("/readiness/manning-board")
    assert response.status_code == 200
    payload = response.json()
    assert "units" in payload
    assert isinstance(payload["units"], list)


def test_post_readiness_coalition_register_200():
    response = client.post(
        "/readiness/coalition/register",
        json={
            "partner_code": 223,
            "personnel": [{"member_id": "UAE-1", "name_en": "Ali", "certifications": ["GCC_WARGAME_L1"]}],
        },
    )
    assert response.status_code == 200
    assert response.json()["registered"] == 1


def test_get_readiness_status_200():
    response = client.get("/readiness/status")
    assert response.status_code == 200
    assert "status" in response.json()
