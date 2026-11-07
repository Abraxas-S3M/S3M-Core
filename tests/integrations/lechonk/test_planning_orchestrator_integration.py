"""Orchestrator ↔ LeChonk planning integration (mock private vLLM only)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.integrations.lechonk.circuit_breaker import CircuitBreaker
from src.integrations.lechonk.orchestrator_routing import PlanningRoutingDecision
from src.integrations.lechonk.planning_backend import LeChonkPlanningBackend
from src.integrations.lechonk.planning_gates import PlanningGateResult
from src.llm_core.backends.vllm_backend import VllmBackend
from src.quad_engine.audit_log import AuditLog
from src.quad_engine.models import EngineStatus, OperationalPacket, PacketType, PLANNING_ENGINE
from src.quad_engine.orchestrator import QuadEngineOrchestrator


def _orch() -> QuadEngineOrchestrator:
    return QuadEngineOrchestrator(audit_log=AuditLog(max_entries=20))


def _open_gates() -> PlanningGateResult:
    routing = PlanningRoutingDecision(
        logical_engine_id="planning_engine",
        backing_engine_id="mistral_large_4",
        used_lechonk=True,
        fallback_reason="",
    )
    return PlanningGateResult(
        may_use_lechonk=True,
        routing=routing,
        rollback_engine_id="mistral",
        reasons=[],
        profile="fp8_gpu",
        runtime_ready=True,
    )


def _mock_backend(text: str, *, success: bool = True, error: str = "") -> LeChonkPlanningBackend:
    backend = VllmBackend(
        model_path="mistral-large-4",
        config={"base_url": "http://127.0.0.1:8000", "lab_mode": True, "internal_hostnames": frozenset()},
    )
    backend._loaded = True  # noqa: SLF001
    backend.generate = MagicMock(  # type: ignore[method-assign]
        return_value={"success": success, "text": text, "error": error}
    )
    backend.health_check = MagicMock(return_value={"reachable": True})  # type: ignore[method-assign]
    return LeChonkPlanningBackend(backend)


def test_orchestrator_uses_mock_vllm_for_coa() -> None:
    structured = (
        '{"coa_options":[{"option_id":"coa-1","name":"Hold","description":"Maintain watch",'
        '"risk":"low","confidence":0.7}]}'
    )
    orch = _orch()
    orch.configure_planning_integration(planning_backend=_mock_backend(structured), planning_gates=_open_gates())
    packet = OperationalPacket(
        packet_id="pkt-lechonk-1",
        packet_type=PacketType.DECISION_REQUEST,
        requested_outputs=["coa_options"],
    )
    result = orch.process_packet(packet)
    assert result.engine_status[PLANNING_ENGINE] == EngineStatus.LIVE_LOCAL
    coa = result.outputs["coa_options"]
    assert coa[0]["name"] == "Hold"
    audit = orch._audit.recent(limit=1)[-1]["details"]  # noqa: SLF001
    assert audit["planning_execution"]["lechonk_success"] is True
    assert audit["planning_execution"]["output_origin"] == "lechonk_vllm"
    assert audit["human_review_required"] is True


def test_orchestrator_fallback_not_labeled_as_lechonk() -> None:
    orch = _orch()
    orch.configure_planning_integration(
        planning_backend=_mock_backend("", success=False, error="timeout"),
        planning_gates=_open_gates(),
    )
    packet = OperationalPacket(packet_id="pkt-fallback", requested_outputs=["coa_options"])
    result = orch.process_packet(packet)
    assert result.engine_status[PLANNING_ENGINE] == EngineStatus.PLACEHOLDER
    desc = result.outputs["coa_options"][0]["description"]
    assert "LEGACY FALLBACK" in desc
    assert "not Le Chonk inference" in desc
    audit = orch._audit.recent(limit=1)[-1]["details"]  # noqa: SLF001
    assert audit["planning_execution"]["lechonk_success"] is False


def test_circuit_open_yields_identified_fallback() -> None:
    backend = VllmBackend(
        model_path="mistral-large-4",
        config={"base_url": "http://127.0.0.1:8000", "lab_mode": True, "internal_hostnames": frozenset()},
    )
    backend._loaded = True  # noqa: SLF001
    adapter = LeChonkPlanningBackend(backend, circuit_breaker=CircuitBreaker(failure_threshold=1))
    adapter._breaker.record_failure()
    adapter._breaker.record_failure()
    orch = _orch()
    orch.configure_planning_integration(planning_backend=adapter, planning_gates=_open_gates())
    packet = OperationalPacket(packet_id="pkt-circuit", requested_outputs=["watch_priorities"])
    result = orch.process_packet(packet)
    assert result.engine_status[PLANNING_ENGINE] == EngineStatus.PLACEHOLDER
    assert "LEGACY FALLBACK" in result.outputs["watch_priorities"][0]


def test_other_engines_remain_placeholder() -> None:
    orch = _orch()
    orch.configure_planning_integration(planning_backend=_mock_backend("ignored"), planning_gates=_open_gates())
    packet = OperationalPacket(
        packet_id="pkt-all",
        requested_outputs=["sitrep", "threat_assessment", "coa_options", "arabic_summary"],
    )
    result = orch.process_packet(packet)
    assert result.engine_status["tactical_engine"] == EngineStatus.PLACEHOLDER
    assert result.engine_status["reasoning_engine"] == EngineStatus.PLACEHOLDER
    assert result.engine_status[PLANNING_ENGINE] == EngineStatus.LIVE_LOCAL
    assert result.engine_status["arabic_engine"] == EngineStatus.PLACEHOLDER
