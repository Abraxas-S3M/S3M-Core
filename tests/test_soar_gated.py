"""Tests for SOAR mutate gating through Cortex PolicyGate."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

from services.cyber.models import CaseSeverity, IncidentCase, Playbook, PlaybookAction, PlaybookStep
from services.cyber.soar.playbook_executor import PlaybookExecutor
from services.cyber.soar.step_classification import classify_playbook_step
from src.cortex.policy_gate import Approvals, MissionEnvelope
from src.security.crypto.secure_audit_log import SecureAuditLog


def _case() -> IncidentCase:
    return IncidentCase(
        title="Contoso breach",
        description="Malware on endpoint",
        severity=CaseSeverity.HIGH,
        source_events=["evt-1"],
    )


def _block_playbook() -> Playbook:
    return Playbook(
        playbook_id="PB-GATE",
        name="Block",
        description="block test",
        trigger_conditions=[],
        steps=[
            PlaybookStep(
                step_id=1,
                name="block ip",
                action=PlaybookAction.BLOCK_IP,
                parameters={"ip": "198.51.100.9"},
            )
        ],
    )


def _envelope(case: IncidentCase) -> MissionEnvelope:
    return MissionEnvelope(
        envelope_id="env-gate",
        mission_id="mission-gate",
        approved_by="commander",
        constraints={
            "case_id": case.case_id,
            "allowed_tools": ["BLOCK_IP"],
        },
    )


def _approvals() -> Approvals:
    return Approvals(
        approval_id="appr-gate",
        approver="soc_lead",
        approved_at=datetime.now(timezone.utc),
        approved_tools=["BLOCK_IP"],
    )


def test_mutate_step_without_envelope_is_queued_not_executed() -> None:
    executor = PlaybookExecutor(auto_execute=False)
    case = _case()
    result = executor.execute(_block_playbook(), case)
    step_result = result["results"][0]
    assert step_result["status"] == "awaiting_approval"
    assert result["steps_queued"] == 1
    assert len(executor.get_approval_queue()) == 1


def test_mutate_step_with_envelope_and_approval_executes_once() -> None:
    executor = PlaybookExecutor(auto_execute=False)
    case = _case()
    playbook = _block_playbook()
    first = executor.execute(
        playbook,
        case,
        mission_envelope=_envelope(case),
        approvals=_approvals(),
        manual_execution=True,
    )
    assert first["results"][0]["status"] == "success"
    second = executor.execute(
        playbook,
        case,
        mission_envelope=_envelope(case),
        approvals=_approvals(),
        manual_execution=True,
    )
    assert second["results"][0]["status"] == "skipped"
    assert second["results"][0]["output"]["reason"] == "mutate_already_executed"


def test_unknown_step_type_treated_as_mutate() -> None:
    kind = classify_playbook_step(PlaybookAction.CUSTOM, parameters={"action": "unknown_widget"})
    assert kind.value == "mutate"


def test_read_step_runs_without_approval() -> None:
    executor = PlaybookExecutor(auto_execute=False)
    case = _case()
    playbook = Playbook(
        playbook_id="PB-READ",
        name="Read",
        description="read",
        trigger_conditions=[],
        steps=[PlaybookStep(step_id=1, name="enrich", action=PlaybookAction.ENRICH_OBSERVABLE)],
    )
    result = executor.execute(playbook, case)
    assert result["results"][0]["status"] == "success"


def test_policy_decision_recorded_in_timeline_and_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audit = SecureAuditLog(log_dir=tmp)
        executor = PlaybookExecutor(auto_execute=False, audit_log=audit)
        case = _case()
        executor.execute(_block_playbook(), case)
        timeline_actions = [entry["action"] for entry in case.timeline]
        assert "policy_gate_decision" in timeline_actions
        assert "mutate_step_queued" in timeline_actions
        entries = audit.query(source="soar_playbook_executor", limit=5)
        assert any(item.get("action") == "soar_policy_gate" for item in entries)
