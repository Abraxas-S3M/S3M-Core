#!/usr/bin/env python3
"""Unit tests for autonomy engagement logic extensions."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from src.autonomy.engagement_logic import AuthorizationMode, EngagementPipeline, ThreatPrioritizer


class _MockPayloadAdapter:
    """Captures operator-authorized payload actions for assertions."""

    def __init__(self) -> None:
        self.calls: list[Dict[str, Any]] = []

    def operator_authorized_action(self, action: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(action)
        self.calls.append(payload)
        return {"ok": True, "echo": payload}


def test_threat_prioritizer_orders_by_composite_urgency() -> None:
    prioritizer = ThreatPrioritizer(max_range_m=2_000.0, max_closing_speed_mps=400.0)
    scores = prioritizer.evaluate_threats(
        [
            {
                "track_id": "far-low",
                "position": [1_500.0, 0.0, 0.0],
                "velocity": [-15.0, 0.0, 0.0],
                "confidence": 0.6,
                "priority": 2.0,
            },
            {
                "track_id": "near-fast",
                "position": [100.0, 0.0, 0.0],
                "velocity": [-180.0, 0.0, 0.0],
                "confidence": 0.9,
                "priority": 8.0,
            },
        ],
        ownship_position=(0.0, 0.0, 0.0),
    )
    assert len(scores) == 2
    assert scores[0].track.track_id == "near-fast"
    assert scores[0].composite_score > scores[1].composite_score


def test_hool_denies_without_active_mission_token() -> None:
    adapter = _MockPayloadAdapter()
    pipeline = EngagementPipeline(payload_adapter=adapter, authorization_mode=AuthorizationMode.HOOL)
    result = pipeline.run_cycle(
        detections=[
            {
                "track_id": "t1",
                "position": [1.0, 0.0, 0.0],
                "velocity": [-300.0, 0.0, 0.0],
                "classification": "hostile",
                "iff_status": "hostile",
                "zone_id": "z1",
                "confidence": 1.0,
                "priority": 10.0,
            }
        ],
        context={
            "ownship_position": [0.0, 0.0, 0.0],
            "rules_of_engagement": "weapons_free",
            "authorized_zones": ["z1"],
        },
    )
    assert result.authorization["authorized"] is False
    assert result.execution["commanded_action"] == "hold_fire"
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["action"] == "hold_fire"


def test_hool_authorizes_when_all_gates_pass() -> None:
    adapter = _MockPayloadAdapter()
    pipeline = EngagementPipeline(payload_adapter=adapter, authorization_mode=AuthorizationMode.HOOL)
    result = pipeline.run_cycle(
        detections=[
            {
                "track_id": "t2",
                "position": [1.0, 0.0, 0.0],
                "velocity": [-300.0, 0.0, 0.0],
                "classification": "hostile",
                "iff_status": "hostile",
                "zone_id": "z2",
                "confidence": 1.0,
                "priority": 10.0,
            }
        ],
        context={
            "ownship_position": [0.0, 0.0, 0.0],
            "rules_of_engagement": "weapons_free",
            "authorized_zones": ["z2"],
            "active_mission_token": {"active": True, "expired": False},
        },
    )
    assert result.authorization["authorized"] is True
    assert result.execution["commanded_action"] == "engage"
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["action"] == "engage"


def test_hotl_respects_operator_veto() -> None:
    adapter = _MockPayloadAdapter()
    pipeline = EngagementPipeline(payload_adapter=adapter, authorization_mode=AuthorizationMode.HOTL)
    result = pipeline.run_cycle(
        detections=[
            {
                "track_id": "t3",
                "position": [80.0, 0.0, 0.0],
                "velocity": [-120.0, 0.0, 0.0],
                "classification": "hostile",
                "iff_status": "hostile",
                "zone_id": "z3",
                "confidence": 0.99,
                "priority": 9.0,
            }
        ],
        context={
            "ownship_position": [0.0, 0.0, 0.0],
            "rules_of_engagement": "weapons_free",
            "authorized_zones": ["z3"],
            "operator_veto": True,
        },
    )
    assert result.authorization["authorized"] is False
    assert result.execution["commanded_action"] == "hold_fire"
    assert len(adapter.calls) == 1
