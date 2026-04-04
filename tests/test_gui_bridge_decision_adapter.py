"""Tests for decision workspace adapter behavior."""

from __future__ import annotations

import asyncio
import sys
import types

from src.api.gui_bridge.adapters.decision_adapter import DecisionAdapter, _score_to_severity
from src.api.gui_bridge.models.gui_schemas import SeverityLevel


class _FakeAutonomyProvider:
    def get_decision_feed(self, limit: int = 500):
        return [
            {
                "id": "d-pending",
                "type": "route_change",
                "risk_score": 0.85,
                "confidence": 0.92,
                "reasoning_snippet": "Route deconfliction required.",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "status": "pending",
                "requires_review": True,
            },
            {
                "id": "d-auto",
                "type": "formation_shift",
                "risk_score": 45,
                "confidence": 77,
                "reasoning_snippet": "Formation spacing optimal.",
                "timestamp": "2026-01-01T00:05:00+00:00",
                "status": "approved",
                "requires_review": False,
            },
            {
                "id": "d-human",
                "type": "handoff",
                "risk_score": 0.65,
                "confidence": 0.61,
                "reasoning_snippet": "Human sign-off completed.",
                "timestamp": "2026-01-01T00:06:00+00:00",
                "status": "approved",
                "requires_review": True,
            },
            {
                "id": "d-veto",
                "type": "engage",
                "risk_score": 0.99,
                "confidence": 0.50,
                "reasoning_snippet": "Rules of engagement mismatch.",
                "timestamp": "2026-01-01T00:07:00+00:00",
                "status": "rejected",
                "requires_review": True,
            },
            {
                "id": "d-stale",
                "type": "hold",
                "risk_score": 0.2,
                "confidence": 0.4,
                "reasoning_snippet": "Legacy state unknown.",
                "timestamp": "2026-01-01T00:08:00+00:00",
                "status": "mystery",
                "requires_review": False,
            },
        ]

    def apply_review_decision(self, decision_id: str, approved: bool, reason: str = ""):
        if decision_id == "missing":
            return {"status": "error", "detail": "Decision not found"}
        return {"status": "ok", "decision_id": decision_id, "review_status": "approved" if approved else "rejected"}


def test_score_to_severity_mapping() -> None:
    assert _score_to_severity(0.85) == SeverityLevel.CRITICAL
    assert _score_to_severity(0.65) == SeverityLevel.HIGH
    assert _score_to_severity(0.45) == SeverityLevel.MEDIUM
    assert _score_to_severity(0.10) == SeverityLevel.LOW


def test_get_queue_shapes_and_counts(monkeypatch) -> None:
    import src.dashboard.providers.autonomy_dash_provider as provider_module

    monkeypatch.setattr(provider_module, "AutonomyDashProvider", _FakeAutonomyProvider)
    adapter = DecisionAdapter()
    payload = adapter.get_queue()

    assert payload["queueCounts"] == {
        "pending": 1,
        "autoApproved": 1,
        "humanApproved": 1,
        "vetoed": 1,
        "stale": 1,
    }
    assert len(payload["decisions"]) == 5
    first = payload["decisions"][0]
    assert first["id"] == "d-pending"
    assert first["risk"] == 85
    assert first["confidence"] == 92


def test_approve_emits_realtime_and_timeline(monkeypatch) -> None:
    import src.dashboard.providers.autonomy_dash_provider as provider_module

    monkeypatch.setattr(provider_module, "AutonomyDashProvider", _FakeAutonomyProvider)

    emitted = []
    timeline_rows = []

    async def _emit_to_gui(event_name: str, payload):
        emitted.append((event_name, payload))

    class _TimelineService:
        def emit(self, **kwargs):
            timeline_rows.append(kwargs)

    monkeypatch.setitem(sys.modules, "src.api.gui_bridge.ws_bridge", types.SimpleNamespace(emit_to_gui=_emit_to_gui))
    monkeypatch.setitem(
        sys.modules,
        "src.api.gui_bridge.timeline_service",
        types.SimpleNamespace(timeline_service=_TimelineService()),
    )

    adapter = DecisionAdapter()
    result = asyncio.run(adapter.approve("d-pending", "Commander confirmed"))
    assert result["status"] == "approved"
    assert emitted == [("decision.updated", {"id": "d-pending", "status": "approved"})]
    assert timeline_rows and timeline_rows[0]["category"] == "decision"


def test_reject_returns_404_on_missing_decision(monkeypatch) -> None:
    import src.dashboard.providers.autonomy_dash_provider as provider_module

    monkeypatch.setattr(provider_module, "AutonomyDashProvider", _FakeAutonomyProvider)
    adapter = DecisionAdapter()
    result = asyncio.run(adapter.reject("missing", "No action"))
    assert result["statusCode"] == 404
    assert "error" in result
