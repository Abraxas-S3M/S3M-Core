"""Quad orchestrator audit includes planning backing metadata."""

from __future__ import annotations

import pytest

from src.quad_engine.audit_log import AuditLog
from src.quad_engine.models import OperationalPacket, PacketType
from src.quad_engine.orchestrator import QuadEngineOrchestrator


def test_process_packet_audits_planning_backing(monkeypatch: pytest.MonkeyPatch) -> None:
    audit = AuditLog(max_entries=10)
    orch = QuadEngineOrchestrator(audit_log=audit)
    packet = OperationalPacket(
        packet_id="pkt-1",
        packet_type=PacketType.DECISION_REQUEST,
        payload={"callsign": "EAGLE-1"},
    )
    orch.process_packet(packet)
    entries = audit.recent(limit=1)
    assert entries
    body = entries[-1]["details"]
    backing = body.get("planning_backing") or {}
    assert backing.get("backing_engine") == "mistral"
    assert backing.get("lechonk") is False
