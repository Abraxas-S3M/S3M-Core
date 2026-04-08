"""Integration tests for S3M unified quad-engine runtime."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict
from unittest.mock import patch

sys.path.insert(0, ".")

from src.llm_core.engine_output import (  # noqa: E402
    ActionCandidate,
    EngineHealth,
    EvidenceItem,
    StateUpdate,
    StructuredEngineOutput,
    ThreatEntity,
    parse_raw_text_to_structured,
)
from src.llm_core.engine_registry import EngineID  # noqa: E402
from src.llm_core.engine_runtime import EngineRuntimeAdapter  # noqa: E402
from src.llm_core.reconciliation_engine import ReconciliationEngine  # noqa: E402
from src.llm_core.shared_state import MissionContext, MissionState  # noqa: E402
from src.llm_core.unified_runtime import MissionRequest, UnifiedRuntime  # noqa: E402


@dataclass
class _FakeInferenceResult:
    """Test helper matching minimal InferenceResult attributes."""

    engine_id: EngineID
    prompt: str
    response: str
    tokens_generated: int
    prompt_tokens: int
    latency_ms: float
    tokens_per_second: float
    model_name: str


class _FakePool:
    """Deterministic fake EnginePool for offline runtime tests."""

    def __init__(self, responses: Dict[EngineID, str]) -> None:
        self.responses = responses

    def query_engine(
        self,
        engine_id: EngineID,
        prompt: str,
        system_prompt=None,
        max_tokens=None,
        temperature: float = 0.7,
    ) -> _FakeInferenceResult:
        del system_prompt, max_tokens, temperature
        text = self.responses.get(engine_id, "[ERROR] Engine not loaded")
        return _FakeInferenceResult(
            engine_id=engine_id,
            prompt=prompt,
            response=text,
            tokens_generated=42,
            prompt_tokens=12,
            latency_ms=7.5,
            tokens_per_second=5.6,
            model_name=engine_id.value,
        )


def _make_structured(
    *,
    engine: str,
    threat: str,
    action: str,
    action_type: str = "defensive",
    confidence: float = 0.8,
    task_id: str = "task-t",
) -> StructuredEngineOutput:
    return StructuredEngineOutput(
        engine_id=engine,
        task_id=task_id,
        raw_text=f"{engine} output",
        health=EngineHealth.HEALTHY,
        confidence=confidence,
        threats=[
            ThreatEntity(
                label=threat,
                category="hostile_force",
                confidence=confidence,
                severity="high",
                provenance_engine=engine,
            )
        ],
        actions=[
            ActionCandidate(
                action=action,
                confidence=confidence,
                action_type=action_type,
                priority=2 if action_type == "defensive" else 6,
            )
        ],
        evidence=[
            EvidenceItem(
                summary=f"Sensor report from {engine}",
                confidence=confidence,
                source="sensor",
                tags=["audit"],
            )
        ],
        state_updates=[StateUpdate(field_path="sector.alpha.status", value=action, confidence=confidence)],
    )


def test_structured_engine_output_schema() -> None:
    output = StructuredEngineOutput(
        engine_id="phi3-medium",
        task_id="task-1",
        raw_text="enemy detected. hold position.",
        health=EngineHealth.HEALTHY,
        confidence=0.81,
        threats=[ThreatEntity(label="enemy", category="hostile_force", confidence=0.81)],
        actions=[ActionCandidate(action="hold", confidence=0.81, action_type="defensive")],
        evidence=[EvidenceItem(summary="sensor feed", confidence=0.74)],
        state_updates=[StateUpdate(field_path="ops.status", value="holding", confidence=0.7)],
        latency_ms=12.0,
        tokens_generated=64,
    )
    payload = output.to_dict()
    assert payload["engine_id"] == "phi3-medium"
    assert payload["health"] == "HEALTHY"
    assert payload["threats"][0]["label"] == "enemy"
    assert payload["actions"][0]["action_type"] == "defensive"
    assert payload["state_updates"][0]["field_path"] == "ops.status"


def test_raw_text_parser() -> None:
    text = (
        "Enemy drone observed near sector 7. confidence: 82%. "
        "Recommend hold and monitor. intel report confirms movement."
    )
    structured = parse_raw_text_to_structured(text, engine_id="grok1-314b", task_id="task-2")
    assert structured.health == EngineHealth.HEALTHY
    assert structured.confidence >= 0.8
    assert any(item.label == "enemy" or item.label == "drone" for item in structured.threats)
    assert any(item.action in {"hold", "monitor"} for item in structured.actions)
    assert len(structured.evidence) >= 1


def test_shared_mission_state() -> None:
    state = MissionState()
    state.set_context(MissionContext(mission_id="m1", mission_type="tactical"))
    one = _make_structured(engine="phi3-medium", threat="enemy", action="hold", confidence=0.7)
    two = _make_structured(engine="grok1-314b", threat="enemy", action="hold", confidence=0.8)
    state.ingest_engine_output(one)
    state.ingest_engine_output(two)

    threats = state.get_authoritative_threats()
    actions = state.get_authoritative_actions()
    assert threats and threats[0].label == "enemy"
    assert actions and actions[0].action == "hold"
    assert state.version >= 4  # init + context + two ingests


def test_reconciliation_threat_conflict() -> None:
    state = MissionState()
    state.set_context(MissionContext(mission_id="m2", mission_type="tactical"))
    recon = ReconciliationEngine()
    outputs = {
        "phi3-medium": _make_structured(
            engine="phi3-medium", threat="drone", action="hold", confidence=0.82
        ),
        "grok1-314b": _make_structured(
            engine="grok1-314b", threat="missile", action="hold", confidence=0.76
        ),
    }
    decision = recon.reconcile(outputs, state)
    assert decision.selected_threat in {"drone", "missile"}
    assert decision.review_status in {"ACCEPT", "REVIEW", "REJECT"}


def test_reconciliation_action_conflict() -> None:
    state = MissionState()
    state.set_context(
        MissionContext(
            mission_id="m3",
            mission_type="tactical",
            rules_of_engagement="weapons_hold",
        )
    )
    recon = ReconciliationEngine()
    outputs = {
        "phi3-medium": _make_structured(
            engine="phi3-medium",
            threat="enemy",
            action="defend",
            action_type="defensive",
            confidence=0.71,
        ),
        "mixtral-8x7b": _make_structured(
            engine="mixtral-8x7b",
            threat="enemy",
            action="strike",
            action_type="offensive",
            confidence=0.92,
        ),
    }
    decision = recon.reconcile(outputs, state)
    assert decision.selected_action == "defend"


def test_degraded_engine_failover() -> None:
    state = MissionState()
    state.set_context(MissionContext(mission_id="m4"))
    recon = ReconciliationEngine()
    outputs = {
        "phi3-medium": _make_structured(
            engine="phi3-medium", threat="enemy", action="hold", confidence=0.75
        ),
        "allam-7b": StructuredEngineOutput(
            engine_id="allam-7b",
            task_id="task-x",
            raw_text="[ERROR] Model not loaded",
            health=EngineHealth.NOT_LOADED,
            confidence=0.0,
        ),
    }
    decision = recon.reconcile(outputs, state)
    assert decision.confidence > 0.0
    assert "allam-7b" not in decision.provenance_engines


def test_engine_runtime_no_simulation() -> None:
    responses = {
        EngineID.PHI3_MEDIUM: "Enemy observed. confidence: 0.8. Recommend hold.",
        EngineID.GROK1: "Threat missile detected. confidence: 0.7. defend.",
    }
    adapter = EngineRuntimeAdapter()
    with patch.object(adapter, "_get_pool", return_value=_FakePool(responses)):
        outputs = adapter.execute_engines(
            engine_ids=[EngineID.PHI3_MEDIUM, EngineID.GROK1],
            prompt="status",
            task_id="task-live",
        )
    assert "Pending live inference" not in outputs[EngineID.PHI3_MEDIUM].raw_text
    assert "simulate" not in outputs[EngineID.PHI3_MEDIUM].raw_text.lower()
    assert outputs[EngineID.PHI3_MEDIUM].health == EngineHealth.HEALTHY


def test_unified_runtime_end_to_end() -> None:
    responses = {
        EngineID.PHI3_MEDIUM: "Enemy movement observed. confidence: 80%. Recommend hold.",
        EngineID.MIXTRAL: "Logistics stable. monitor and secure sector.",
    }
    runtime = UnifiedRuntime(runtime_adapter=EngineRuntimeAdapter())
    with patch.object(runtime.runtime_adapter, "_get_pool", return_value=_FakePool(responses)):
        result = runtime.execute_mission(
            MissionRequest(
                prompt="Enemy contact in sector alpha",
                mission_type="tactical",
                rules_of_engagement="weapons_hold",
            )
        )

    payload = result.to_dict()
    assert payload["mission_id"].startswith("mission-")
    assert len(payload["audit_log"]) >= 8
    assert "decision_text" in payload["decision"]
    assert payload["state_snapshot"]["version"] >= 3


def test_reconciliation_agreement_bonus() -> None:
    state = MissionState()
    state.set_context(MissionContext(mission_id="m5"))
    recon = ReconciliationEngine()
    outputs = {
        "phi3-medium": _make_structured(
            engine="phi3-medium", threat="enemy", action="hold", confidence=0.6
        ),
        "grok1-314b": _make_structured(
            engine="grok1-314b", threat="enemy", action="hold", confidence=0.6
        ),
    }
    decision = recon.reconcile(outputs, state)
    assert decision.confidence > 0.6


def test_state_version_history() -> None:
    state = MissionState()
    state.set_context(MissionContext(mission_id="m6"))
    state.ingest_engine_output(
        _make_structured(engine="phi3-medium", threat="enemy", action="hold", confidence=0.7)
    )
    snap = state.snapshot()
    history = snap["version_history"]
    assert len(history) == state.version
    assert history[-1]["reason"] in {"engine_output_ingested", "decision_recorded", "conflict_resolved"}
