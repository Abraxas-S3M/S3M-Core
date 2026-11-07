"""SOAR path tests for Cortex policy gate."""

from __future__ import annotations

from datetime import datetime, timezone

from src.cortex.policy_gate import Approvals, MissionEnvelope, ToolCall, evaluate_soar_tool_call


def test_evaluate_soar_queues_without_envelope() -> None:
    tool = ToolCall(tool_name="BLOCK_IP", case_id="case-1", step_id=1, step_kind="mutate")
    decision = evaluate_soar_tool_call(
        tool,
        None,
        Approvals("a1", "lead", datetime.now(timezone.utc), ["BLOCK_IP"]),
        auto_execute=True,
    )
    assert decision.outcome == "queue"


def test_evaluate_soar_allows_with_envelope_and_approval() -> None:
    tool = ToolCall(tool_name="BLOCK_IP", case_id="case-1", step_id=1, step_kind="mutate")
    envelope = MissionEnvelope(
        envelope_id="env-1",
        mission_id="m-1",
        approved_by="commander",
        constraints={"case_id": "case-1", "allowed_tools": ["BLOCK_IP"]},
    )
    approvals = Approvals("a1", "lead", datetime.now(timezone.utc), ["BLOCK_IP"])
    decision = evaluate_soar_tool_call(tool, envelope, approvals, auto_execute=True)
    assert decision.allowed is True
