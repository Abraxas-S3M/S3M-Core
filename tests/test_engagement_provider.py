"""Unit tests for engagement dashboard provider snapshots."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.engagement_provider import EngagementProvider
from src.dashboard.providers.runtime_store import reset_runtime_state, set_decisions, set_threats


def setup_function() -> None:
    reset_runtime_state()


def test_engagement_snapshot_has_required_sections() -> None:
    set_threats(
        [
            {
                "event_id": "trk-1",
                "level": "HIGH",
                "category": "KINETIC",
                "classification": "hostile",
                "confidence": 0.9,
                "location": {"x": 100.0, "y": 200.0, "z": 50.0},
            }
        ]
    )
    set_decisions(
        [
            {
                "id": "dec-1",
                "type": "engage",
                "confidence": 0.82,
                "risk_score": 0.2,
                "requires_review": False,
                "reasoning": "priority target within authorized zone",
                "context": {"rules_of_engagement": "weapons_free"},
            }
        ]
    )
    provider = EngagementProvider()
    snapshot = provider.get_snapshot()
    assert snapshot["provider"] == "engagement"
    assert "recommendations" in snapshot
    assert "track_picture" in snapshot
    assert "interlock_states" in snapshot
    assert "active_roe_profile" in snapshot
    assert snapshot["track_picture"]["total"] >= 1
    assert snapshot["active_roe_profile"] == "weapons_free"


def test_engagement_recommendations_fallback_to_runtime_decisions() -> None:
    set_decisions(
        [
            {
                "id": "dec-2",
                "type": "hold_fire",
                "confidence": 0.7,
                "risk_score": 0.4,
                "requires_review": True,
                "reasoning_snippet": "uncertain target identity",
            }
        ]
    )
    provider = EngagementProvider()
    snapshot = provider.get_snapshot()
    assert snapshot["recommendations"]
    first = snapshot["recommendations"][0]
    assert first["recommendation_id"] == "dec-2"
    assert first["commanded_action"] == "hold_fire"
