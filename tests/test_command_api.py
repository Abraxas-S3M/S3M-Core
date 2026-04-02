"""API tests for Mission Command Engine command routes."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.api.server import app


def test_command_ingest_and_cop_snapshot():
    client = TestClient(app)
    event_payload = {
        "event_type": "THREAT_DETECTED",
        "source_layer": "layer-02",
        "payload": {
            "threat_id": "thr-api-001",
            "description": "Hostile emitter detected near corridor bravo",
            "lethal_response_requested": False,
        },
    }

    ingest = client.post("/command/ingest", json=event_payload)
    assert ingest.status_code == 200
    ingest_data = ingest.json()
    assert ingest_data["status"] == "ingested"
    assert "event_id" in ingest_data

    # Tactical context: command processing is asynchronous, so poll briefly for COP convergence.
    cop_data = {}
    for _ in range(30):
        cop = client.get("/command/cop")
        assert cop.status_code == 200
        cop_data = cop.json()
        if "thr-api-001" in cop_data.get("threats", {}):
            break
        time.sleep(0.05)

    assert "threats" in cop_data
    assert "thr-api-001" in cop_data["threats"]
    assert cop_data["threats"]["thr-api-001"]["description"] == "Hostile emitter detected near corridor bravo"


def test_command_pending_and_approve_missing_ticket():
    client = TestClient(app)

    pending = client.get("/command/pending")
    assert pending.status_code == 200
    assert isinstance(pending.json(), list)

    approve = client.post(
        "/command/approve",
        json={"ticket_id": "missing-ticket", "granted": True, "resolver": "ops-chief"},
    )
    assert approve.status_code == 404
    assert "detail" in approve.json()
