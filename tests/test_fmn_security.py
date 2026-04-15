"""Unit tests for FMN security labels, identity, manager, and API routes."""

from __future__ import annotations

import json
import pytest

from services.interop.fmn_security import (
    CoalitionIdentityProvider,
    FMNSecurityManager,
    NATOSecurityLabel,
)
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.fmn_security_routes import fmn_security_router
except ModuleNotFoundError:  # pragma: no cover - dependency optional in minimal env
    TestClient = None  # type: ignore[assignment]
    client = None
else:
    _route_app = FastAPI()
    _route_app.include_router(fmn_security_router)
    client = TestClient(_route_app)


def test_nato_security_label_round_trip_xml_and_access() -> None:
    label = NATOSecurityLabel(
        classification="NATO SECRET",
        policy_identifier="NATO",
        releasable_to=["SAU", "USA"],
        caveats=["REL TO SAU, USA"],
    )
    xml_str = label.to_xml()
    parsed = NATOSecurityLabel.from_xml(xml_str)
    assert parsed.build_label() == label.build_label()
    assert parsed.validate_access("NATO SECRET", "SAU") is True
    assert parsed.validate_access("NATO SECRET", "GBR") is False


def test_nato_security_label_rejects_invalid_nation() -> None:
    try:
        NATOSecurityLabel(
            classification="NATO SECRET",
            policy_identifier="NATO",
            releasable_to=["SA"],
            caveats=[],
        )
    except ValueError as exc:
        assert "ISO 3166 alpha-3" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid releasable_to code")


def test_coalition_identity_register_validate_and_authorize() -> None:
    provider = CoalitionIdentityProvider()
    user = provider.register_coalition_user(
        user_id="falcon-1",
        nation="sau",
        clearance="NATO SECRET",
        roles=["interop_operator"],
    )
    assert user["nation"] == "SAU"
    token = provider.validate_token("SAML|falcon-1|SAU|NATO SECRET|VALID")
    assert token["token_valid"] is True
    assert (
        provider.check_authorization(
            {"clearance": "NATO SECRET", "roles": ["interop_operator"]},
            "NATO CONFIDENTIAL",
            "publish_track",
        )
        is True
    )


def test_coalition_identity_certificate_authentication_shape() -> None:
    provider = CoalitionIdentityProvider()
    cert_payload = "QUJDRA=="  # "ABCD" bytes
    cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_payload}\n-----END CERTIFICATE-----\n"
    identity = provider.authenticate_certificate(cert_pem)
    assert identity["auth_method"] == "x509_certificate"
    assert identity["user_id"].startswith("cert-")
    assert len(identity["certificate_fingerprint_sha256"]) == 64


def test_fmn_security_manager_label_validate_and_enforce() -> None:
    manager = FMNSecurityManager({"enforce_labels": True})
    labeled = manager.label_message("interop payload", "NATO SECRET", ["SAU", "USA"])
    ok, reason = manager.validate_incoming(labeled)
    assert ok is True
    assert "valid" in reason

    payload = json.loads(labeled)
    allowed = manager.enforce_policy(
        operation="publish_track",
        user={
            "user_id": "falcon-2",
            "nation": "SAU",
            "clearance": "NATO SECRET",
            "roles": ["interop_operator"],
        },
        data={
            "required_clearance": "NATO CONFIDENTIAL",
            "security_label": payload["_fmn_security_label"],
        },
    )
    denied = manager.enforce_policy(
        operation="publish_track",
        user={
            "user_id": "falcon-3",
            "nation": "GBR",
            "clearance": "NATO SECRET",
            "roles": ["interop_operator"],
        },
        data={
            "required_clearance": "NATO CONFIDENTIAL",
            "security_label": payload["_fmn_security_label"],
        },
    )
    assert allowed is True
    assert denied is False


def test_post_fmn_label_message_200() -> None:
    if client is None:
        pytest.skip("fastapi not installed")
    response = client.post(
        "/security/fmn/label",
        json={
            "message": "<CoT event='sample'/>",
            "classification": "NATO SECRET",
            "releasable_to": ["SAU", "USA"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "labeled_message" in payload
    assert "_fmn_security_label" in payload["labeled_message"]


def test_post_fmn_validate_message_200() -> None:
    if client is None:
        pytest.skip("fastapi not installed")
    labeled_resp = client.post(
        "/security/fmn/label",
        json={
            "message": "<NFFI track='A1'/>",
            "classification": "NATO CONFIDENTIAL",
            "releasable_to": ["SAU"],
        },
    )
    labeled = labeled_resp.json()["labeled_message"]
    response = client.post("/security/fmn/validate", json={"message": labeled})
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True


def test_post_fmn_authorize_200_false_when_not_releasable() -> None:
    if client is None:
        pytest.skip("fastapi not installed")
    response = client.post(
        "/security/fmn/enforce",
        json={
            "operation": "publish_track",
            "user": {
                "user_id": "falcon-4",
                "nation": "GBR",
                "clearance": "NATO SECRET",
                "roles": ["interop_operator"],
            },
            "data": {
                "required_clearance": "NATO CONFIDENTIAL",
                "security_label": {
                    "classification": "NATO CONFIDENTIAL",
                    "policy_identifier": "NATO",
                    "releasable_to": ["SAU"],
                    "caveats": [],
                },
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False


def test_post_fmn_register_user_and_roster_200() -> None:
    if client is None:
        pytest.skip("fastapi not installed")
    register_resp = client.post(
        "/security/fmn/users/register",
        json={
            "user_id": "falcon-5",
            "nation": "SAU",
            "clearance": "NATO RESTRICTED",
            "roles": ["interop_operator"],
        },
    )
    assert register_resp.status_code == 200
    assert register_resp.json()["user"]["user_id"] == "falcon-5"

    roster_resp = client.get("/security/fmn/users/roster")
    assert roster_resp.status_code == 200
    roster = roster_resp.json()["users"]
    assert any(entry["user_id"] == "falcon-5" for entry in roster)
