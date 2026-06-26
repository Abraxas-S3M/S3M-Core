"""Unit tests for the S3M-Core Quad-Engine Orchestration Demo Layer.

Tactical context:
    These tests lock down the demo orchestration contract: packet classification
    and routing, deterministic placeholder generation when no local model is
    present, the four-engine status panel, the COP commander brief, and the
    hard safety guarantees (human review required, no autonomous action, no
    external/training paths exercised, local LLM disabled by default).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.quad_engine.audit_log import AuditLog
from src.quad_engine.model_registry import ModelRegistry
from src.quad_engine.models import (
    ARABIC_ENGINE,
    ENGINE_IDS,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    EngineStatus,
    OperationalPacket,
    PacketType,
)
from src.quad_engine.orchestrator import QuadEngineOrchestrator
from src.quad_engine.packet_router import PacketRouter
from src.quad_engine.routes import router as quad_engine_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(quad_engine_router)
    return app


# ── Registry ─────────────────────────────────────────────────

def test_registry_has_four_engines_in_placeholder_by_default() -> None:
    registry = ModelRegistry(models_dir="/nonexistent/models/dir")
    assert set(registry.engine_ids()) == set(ENGINE_IDS)
    for eid in ENGINE_IDS:
        assert registry.effective_status(eid) == EngineStatus.PLACEHOLDER


def test_registry_rejects_path_traversal_in_model_file(tmp_path) -> None:
    from src.quad_engine.models import EngineRole, ModelRegistryEntry

    evil = ModelRegistryEntry(
        engine_id="evil",
        display_name="evil",
        model_file="../../etc/passwd",
        role=EngineRole.TACTICAL,
    )
    registry = ModelRegistry(entries=[evil], models_dir=str(tmp_path))
    assert registry.resolve_model_path("evil") is None
    assert registry.model_present("evil") is False


def test_registry_resolves_present_model(tmp_path) -> None:
    from src.quad_engine.models import EngineRole, ModelRegistryEntry

    model_file = tmp_path / "phi-3-mini-q4_k_m.gguf"
    model_file.write_text("stub")
    entry = ModelRegistryEntry(
        engine_id=TACTICAL_ENGINE,
        display_name="t",
        model_file="phi-3-mini-q4_k_m.gguf",
        role=EngineRole.TACTICAL,
    )
    registry = ModelRegistry(entries=[entry], models_dir=str(tmp_path))
    assert registry.model_present(TACTICAL_ENGINE) is True
    # Without S3M_ENABLE_LOCAL_LLM=true, status stays placeholder.
    os.environ.pop("S3M_ENABLE_LOCAL_LLM", None)
    assert registry.effective_status(TACTICAL_ENGINE) == EngineStatus.PLACEHOLDER


# ── Router ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("packet_type", "primary"),
    [
        (PacketType.TRACK_UPDATE, TACTICAL_ENGINE),
        (PacketType.ALERT, REASONING_ENGINE),
        (PacketType.DECISION_REQUEST, PLANNING_ENGINE),
        (PacketType.FEED, TACTICAL_ENGINE),
        (PacketType.OPERATOR_NOTE, TACTICAL_ENGINE),
    ],
)
def test_router_selects_expected_primary_engine(packet_type, primary) -> None:
    packet = OperationalPacket(packet_id="pkt-1", packet_type=packet_type)
    route = PacketRouter().route(packet)
    assert route.primary_engine == primary
    assert primary not in route.supporting_engines
    assert route.reason


# ── Orchestrator placeholder behavior ────────────────────────

def _fresh_orchestrator() -> QuadEngineOrchestrator:
    os.environ.pop("S3M_ENABLE_LOCAL_LLM", None)
    return QuadEngineOrchestrator(
        registry=ModelRegistry(models_dir="/nonexistent/models/dir"),
        audit_log=AuditLog(),
    )


def test_process_packet_returns_structured_output_without_models() -> None:
    orch = _fresh_orchestrator()
    packet = OperationalPacket(
        packet_id="pkt-demo-001",
        source="cop",
        track="saudi_mod",
        packet_type=PacketType.TRACK_UPDATE,
        requested_outputs=["sitrep", "threat_assessment", "coa_options", "arabic_summary"],
    )
    result = orch.process_packet(packet)

    assert result.packet_id == "pkt-demo-001"
    assert result.route.primary_engine == TACTICAL_ENGINE
    assert set(result.outputs.keys()) == {
        "sitrep",
        "threat_assessment",
        "coa_options",
        "arabic_summary",
    }
    assert isinstance(result.outputs["coa_options"], list) and result.outputs["coa_options"]
    # Safety guarantees
    assert result.human_review_required is True
    assert all(c.status == "human_review_required" for c in result.decision_cards)
    assert set(result.engine_status.keys()) == set(ENGINE_IDS)
    assert all(s == EngineStatus.PLACEHOLDER for s in result.engine_status.values())
    assert 0.0 <= result.confidence <= 1.0


def test_process_packet_is_retrievable_by_id() -> None:
    orch = _fresh_orchestrator()
    result = orch.process_packet(OperationalPacket(packet_id="pkt-2"))
    fetched = orch.get_result(result.result_id)
    assert fetched is not None
    assert fetched.result_id == result.result_id


def test_cop_brief_summarizes_demo_state() -> None:
    orch = _fresh_orchestrator()
    cop_state = {
        "track": "saudi_mod",
        "tactical_tracks": [
            {"domain": "air", "affiliation": "hostile"},
            {"domain": "maritime", "affiliation": "unknown"},
            {"domain": "isr", "affiliation": "friendly"},
        ],
        "alerts": [{"title": "Air threat", "status": "active"}],
        "decisions": [{"title": "Review escalation", "summary": "x", "priority": "high"}],
    }
    result = orch.build_cop_brief(cop_state)
    assert "sitrep" in result.outputs
    assert "threat_assessment" in result.outputs
    assert "watch_priorities" in result.outputs
    assert "arabic_summary" in result.outputs
    assert result.human_review_required is True
    assert any(c.title == "No autonomous action taken" for c in result.decision_cards)


# ── Local LLM safety ─────────────────────────────────────────

def test_local_llm_disabled_by_default() -> None:
    os.environ.pop("S3M_ENABLE_LOCAL_LLM", None)
    from src.quad_engine.local_llm import LocalLLMRunner

    runner = LocalLLMRunner(registry=ModelRegistry(models_dir="/nonexistent"))
    assert runner.enabled is False
    assert runner.runner_available() is False
    assert runner.generate(TACTICAL_ENGINE, "prompt") is None


# ── API routes ───────────────────────────────────────────────

def test_status_endpoint_returns_safe_posture() -> None:
    os.environ.pop("S3M_ENABLE_LOCAL_LLM", None)
    client = TestClient(_build_app())
    response = client.get("/api/quad-engine/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "operational"
    assert body["autonomous_action_enabled"] is False
    assert body["external_apis_called"] is False
    assert body["human_review_required"] is True


def test_engines_endpoint_returns_four_records() -> None:
    client = TestClient(_build_app())
    response = client.get("/api/quad-engine/engines")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert {e["engine_id"] for e in body["engines"]} == set(ENGINE_IDS)


def test_packet_endpoint_returns_structured_ai_output() -> None:
    client = TestClient(_build_app())
    response = client.post(
        "/api/quad-engine/packet",
        json={
            "packet_id": "pkt-demo-001",
            "source": "cop",
            "track": "saudi_mod",
            "packet_type": "track_update",
            "classification": "UNCLASSIFIED_DEMO",
            "payload": {"affiliation": "unknown", "domain": "air"},
            "requested_outputs": ["sitrep", "threat_assessment", "coa_options", "arabic_summary"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["packet_id"] == "pkt-demo-001"
    assert body["human_review_required"] is True
    assert "sitrep" in body["outputs"]

    # Result must then be retrievable.
    rid = body["result_id"]
    fetched = client.get(f"/api/quad-engine/results/{rid}")
    assert fetched.status_code == 200


def test_results_endpoint_404_for_unknown() -> None:
    client = TestClient(_build_app())
    response = client.get("/api/quad-engine/results/does-not-exist")
    assert response.status_code == 404


def test_cop_brief_endpoint_returns_commander_brief() -> None:
    client = TestClient(_build_app())
    response = client.post("/api/quad-engine/demo/cop-brief", json={"track": "saudi_mod"})
    assert response.status_code == 200
    body = response.json()
    assert body["outputs"]["sitrep"]
    assert body["human_review_required"] is True
    assert len(body["engine_status"]) == 4


def test_audit_endpoint_records_activity() -> None:
    client = TestClient(_build_app())
    client.post("/api/quad-engine/packet", json={"packet_id": "pkt-audit-1"})
    response = client.get("/api/quad-engine/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(log["action"] == "quad_engine_packet" for log in body["logs"])
