#!/usr/bin/env python3
"""API tests for S3M Phase 14 secure communications routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app


def _register_seed_node(client: TestClient, callsign: str = "COMMAND-ALPHA") -> None:
    client.post(
        "/comms/nodes",
        json={
            "callsign": callsign,
            "node_type": "command_center",
            "relay_backends": ["simulated"],
            "position": [0.0, 0.0, 0.0],
        },
    )


def test_post_comms_send() -> None:
    client = TestClient(app)
    _register_seed_node(client)
    response = client.post(
        "/comms/send",
        json={
            "sender_callsign": "COMMAND-ALPHA",
            "recipients": ["WOLF-01"],
            "body": "Move to checkpoint Bravo.",
            "message_type": "ORDER",
            "priority": "PRIORITY",
            "language": "en",
            "encrypt": True,
        },
    )
    assert response.status_code == 200
    assert "message_id" in response.json()


def test_post_comms_order() -> None:
    client = TestClient(app)
    _register_seed_node(client)
    response = client.post(
        "/comms/order",
        json={
            "sender": "COMMAND-ALPHA",
            "recipients": ["EAGLE-01"],
            "order_text": "Patrol sector Alpha.",
            "priority": "IMMEDIATE",
        },
    )
    assert response.status_code == 200


def test_post_comms_alert() -> None:
    client = TestClient(app)
    _register_seed_node(client)
    response = client.post("/comms/alert", json={"sender": "COMMAND-ALPHA", "alert_text": "IED threat reported."})
    assert response.status_code == 200


def test_get_comms_messages() -> None:
    client = TestClient(app)
    response = client.get("/comms/messages")
    assert response.status_code == 200
    payload = response.json()
    assert "messages" in payload


def test_post_comms_channels() -> None:
    client = TestClient(app)
    response = client.post(
        "/comms/channels",
        json={"name": "COMMAND-NET", "channel_type": "COMMAND_NET", "members": ["COMMAND-ALPHA", "WOLF-01"]},
    )
    assert response.status_code == 200
    assert "channel_id" in response.json()


def test_get_comms_channels() -> None:
    client = TestClient(app)
    response = client.get("/comms/channels")
    assert response.status_code == 200


def test_post_comms_nodes() -> None:
    client = TestClient(app)
    response = client.post(
        "/comms/nodes",
        json={"callsign": "WOLF-01", "node_type": "field_unit", "relay_backends": ["simulated"], "position": [1.0, 1.0, 0.0]},
    )
    assert response.status_code == 200
    assert "node_id" in response.json()


def test_get_comms_nodes() -> None:
    client = TestClient(app)
    response = client.get("/comms/nodes")
    assert response.status_code == 200


def test_get_comms_nodes_topology() -> None:
    client = TestClient(app)
    response = client.get("/comms/nodes/topology")
    assert response.status_code == 200


def test_get_comms_status() -> None:
    client = TestClient(app)
    response = client.get("/comms/status")
    assert response.status_code == 200


def test_get_comms_backends() -> None:
    client = TestClient(app)
    response = client.get("/comms/backends")
    assert response.status_code == 200


def test_get_comms_brief() -> None:
    client = TestClient(app)
    response = client.get("/comms/brief")
    assert response.status_code == 200


def test_post_comms_nlp_summarize() -> None:
    client = TestClient(app)
    response = client.post("/comms/nlp/summarize", json={"text": "Enemy contact at grid 5000,3000.", "language": "en"})
    assert response.status_code == 200
    assert "summary_en" in response.json()


def test_get_comms_nlp_model() -> None:
    client = TestClient(app)
    response = client.get("/comms/nlp/model")
    assert response.status_code == 200
    assert "model_info" in response.json()
