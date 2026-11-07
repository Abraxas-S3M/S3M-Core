"""Unit tests for Cortex PolicyGate."""

from __future__ import annotations

from src.cortex.policy_gate import Approval, MissionEnvelope, PolicyGate


def test_mutating_action_requires_envelope() -> None:
    verdict = PolicyGate.evaluate(
        {
            "tool_name": "file_delete",
            "risk_level": "high",
            "autonomy_level": "bounded",
            "parameters": {"path": "/workspace/x"},
        }
    )
    assert not verdict.allowed
    assert "mission_envelope" in verdict.reason


def test_valid_write_requires_distinct_oob_approver() -> None:
    verdict = PolicyGate.evaluate(
        {
            "tool_name": "file_write",
            "risk_level": "medium",
            "autonomy_level": "bounded",
            "proposer": "orchestrator",
            "mission_envelope": MissionEnvelope(
                envelope_id="env-1",
                mission_id="mission-1",
                approved_by="commander",
            ),
            "approvals": [
                Approval(
                    approver="operator-1",
                    proposer="orchestrator",
                    channel="out_of_band_device",
                )
            ],
            "parameters": {"path": "/workspace/a", "content": "x"},
        }
    )
    assert verdict.allowed
