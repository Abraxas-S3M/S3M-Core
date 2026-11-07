"""Fail-closed policy gate tests for agentic orchestrator authority."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from s3m_core.agents.orchestrator import AgenticOrchestrator  # noqa: E402
from s3m_core.agents.subagent import PermissionSet, SubAgent, SubTask  # noqa: E402
from s3m_core.agents.tool_registry import ToolRegistry  # noqa: E402
from s3m_core.defense.audit.merkle_log import MerkleAuditLog  # noqa: E402
from src.cortex.policy_gate import Approval, MissionEnvelope  # noqa: E402


class _BrokenGate:
    def approve(self, _: dict) -> bool:
        raise RuntimeError("gate failure")


class _NoCallableGate:
    """Gate object without any policy method."""


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(
        name="intel_lookup",
        handler=lambda params: {"intel": params.get("task_description", "")},
        risk_level="low",
        description="Lookup",
        parameter_schema={},
    )
    return registry


def _orchestrator(
    *,
    action_gate,
    deliberation_gate,
    audit_path: Path | None = None,
    permissions: PermissionSet | None = None,
    autonomy_level: str = "bounded",
) -> AgenticOrchestrator:
    audit_log = MerkleAuditLog(str(audit_path)) if audit_path is not None else None
    return AgenticOrchestrator(
        model=None,
        tokenizer=None,
        tool_registry=_registry(),
        action_gate=action_gate,
        deliberation_gate=deliberation_gate,
        sae_monitor=None,
        emotion_probe=None,
        permission_set=permissions
        or PermissionSet(allowed_tools=["intel_lookup", "file_write"], allowed_paths=["/workspace"]),
        audit_log=audit_log,
    )


def test_unconfigured_gate_denies() -> None:
    orchestrator = _orchestrator(action_gate=None, deliberation_gate=None)
    orchestrator._current_autonomy_level = "bounded"
    ok, reason = orchestrator._approve_action(
        {"tool_name": "intel_lookup", "risk_level": "low", "parameters": {}},
        proposer="orchestrator",
    )
    assert not ok
    assert "not_configured" in reason


def test_gate_without_callable_denies() -> None:
    orchestrator = _orchestrator(action_gate=_NoCallableGate(), deliberation_gate=_NoCallableGate())
    orchestrator._current_autonomy_level = "bounded"
    ok, reason = orchestrator._approve_action(
        {"tool_name": "intel_lookup", "risk_level": "low", "parameters": {}},
        proposer="orchestrator",
    )
    assert not ok
    assert "no_callable" in reason


def test_gate_exception_denies() -> None:
    orchestrator = _orchestrator(action_gate=_BrokenGate(), deliberation_gate=_BrokenGate())
    orchestrator._current_autonomy_level = "bounded"
    ok, reason = orchestrator._approve_action(
        {"tool_name": "intel_lookup", "risk_level": "low", "parameters": {}},
        proposer="orchestrator",
    )
    assert not ok
    assert "gate failure" in reason


def test_bounded_mode_denies_write_without_envelope() -> None:
    class ApproveGate:
        def approve(self, _: dict) -> bool:
            return True

    orchestrator = _orchestrator(action_gate=ApproveGate(), deliberation_gate=ApproveGate())
    orchestrator._current_autonomy_level = "bounded"
    ok, reason = orchestrator._approve_action(
        {
            "tool_name": "file_write",
            "risk_level": "medium",
            "parameters": {"path": "/workspace/out.txt", "content": "x"},
        },
        proposer="orchestrator",
    )
    assert not ok
    assert "mission_envelope" in reason


def test_self_set_human_approved_cannot_authorize_write() -> None:
    class ApproveGate:
        def approve(self, _: dict) -> bool:
            return True

    orchestrator = _orchestrator(action_gate=ApproveGate(), deliberation_gate=ApproveGate())
    orchestrator._current_autonomy_level = "semi_autonomous"
    ok, reason = orchestrator._approve_action(
        {
            "tool_name": "file_write",
            "risk_level": "medium",
            "parameters": {
                "path": "/workspace/out.txt",
                "content": "x",
                "human_approved": True,
                "mission_envelope": MissionEnvelope(
                    envelope_id="env-1",
                    mission_id="mission-1",
                    approved_by="commander",
                ),
            },
        },
        proposer="orchestrator",
    )
    assert not ok
    assert "out-of-band" in reason


def test_write_allowed_with_envelope_and_oob_approval(tmp_path: Path) -> None:
    class ApproveGate:
        def approve(self, _: dict) -> bool:
            return True

    log_path = tmp_path / "audit.jsonl"
    orchestrator = _orchestrator(
        action_gate=ApproveGate(),
        deliberation_gate=ApproveGate(),
        audit_path=log_path,
    )
    orchestrator._current_autonomy_level = "bounded"
    ok, reason = orchestrator._approve_action(
        {
            "tool_name": "file_write",
            "risk_level": "medium",
            "mission_envelope": MissionEnvelope(
                envelope_id="env-2",
                mission_id="mission-2",
                approved_by="commander",
            ),
            "approvals": [
                Approval(
                    approver="human-operator",
                    proposer="orchestrator",
                    channel="out_of_band_device",
                    approved_at=datetime.now(timezone.utc),
                )
            ],
            "parameters": {"path": "/workspace/out.txt", "content": "payload"},
        },
        proposer="orchestrator",
    )
    assert ok
    assert "authorized" in reason
    report = MerkleAuditLog(str(log_path)).verify_integrity()
    assert report.chain_intact


def test_subagent_cannot_widen_parent_permissions() -> None:
    class Parent:
        permission_set = PermissionSet(
            allowed_tools=["file_read"],
            allowed_paths=["/workspace"],
            network_allowlist=[],
            max_tokens=1024,
            timeout_seconds=120,
        )

    with pytest.raises(ValueError, match="restrictive"):
        SubAgent(
            agent_id="child",
            model=None,
            tokenizer=None,
            parent_orchestrator=Parent(),
            task=SubTask(task_id="t1", description="analyze"),
            tools=["file_read", "file_write"],
            permissions=PermissionSet(
                allowed_tools=["file_read", "file_write"],
                allowed_paths=["/workspace"],
                network_allowlist=[],
                max_tokens=1024,
                timeout_seconds=120,
            ),
        )


def test_parent_empty_permissions_rejects_child_tool_grant() -> None:
    class Parent:
        permission_set = PermissionSet(
            allowed_tools=[],
            allowed_paths=[],
            network_allowlist=[],
            max_tokens=1024,
            timeout_seconds=120,
        )

    with pytest.raises(ValueError, match="restrictive"):
        SubAgent(
            agent_id="child",
            model=None,
            tokenizer=None,
            parent_orchestrator=Parent(),
            task=SubTask(task_id="t1", description="analyze"),
            tools=["file_read"],
            permissions=PermissionSet(
                allowed_tools=["file_read"],
                allowed_paths=[],
                network_allowlist=[],
                max_tokens=1024,
                timeout_seconds=120,
            ),
        )
