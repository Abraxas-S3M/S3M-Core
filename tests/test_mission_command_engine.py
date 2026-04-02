"""Unit tests for Mission Command Engine core behaviors."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from src.command.mission_command_engine import (
    ApprovalGate,
    ApprovalState,
    AuthoritativeState,
    AuditLog,
    EventType,
    MCEvent,
    MissionCommandEngine,
)


def _reset_mce() -> MissionCommandEngine:
    """Reset singleton state to keep tests deterministic."""
    mce = MissionCommandEngine()
    mce.state = AuthoritativeState()
    mce.gate = ApprovalGate()
    mce.audit = AuditLog(log_path="data/test_mce_audit.jsonl")
    mce._queue = asyncio.Queue()
    mce.stop()
    return mce


def test_mce_ingest_updates_cop_threats():
    async def _scenario():
        mce = _reset_mce()
        runner = asyncio.create_task(mce.start())
        try:
            await mce.ingest(
                MCEvent(
                    event_type=EventType.THREAT_DETECTED,
                    source_layer="layer-02",
                    payload={"threat_id": "thr-unit-001", "severity": "HIGH"},
                )
            )
            await asyncio.wait_for(mce._queue.join(), timeout=2.0)
            snapshot = mce.get_cop_snapshot()
            assert "thr-unit-001" in snapshot["threats"]
            assert snapshot["threats"]["thr-unit-001"]["severity"] == "HIGH"
        finally:
            mce.stop()
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner

    asyncio.run(_scenario())


def test_mce_resolve_approval_marks_ticket_granted():
    async def _scenario():
        mce = _reset_mce()
        ticket = mce.gate.create_ticket(
            action="LETHAL_ENGAGE",
            requestor="layer-02",
            payload={"target_id": "tgt-100"},
        )
        resolved = await mce.resolve_approval(
            ticket_id=ticket.ticket_id,
            granted=True,
            resolver="ops-chief",
        )
        assert resolved is not None
        assert resolved.state == ApprovalState.GRANTED
        assert resolved.resolver == "ops-chief"
        assert all(t.ticket_id != ticket.ticket_id for t in mce.gate.get_pending())

    asyncio.run(_scenario())
