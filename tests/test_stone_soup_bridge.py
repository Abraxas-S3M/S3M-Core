"""Unit tests for Stone Soup bridge identity fallback behavior."""

from __future__ import annotations

from src.sensor_fusion.stone_soup_bridge import StoneSoupBridge


def test_identity_probabilities_fallback_to_uniform_when_stonesoup_missing() -> None:
    bridge = StoneSoupBridge()
    bridge._stonesoup_available = False  # type: ignore[attr-defined]

    probabilities = bridge.get_identity_probabilities("TRK-001")

    assert set(probabilities.keys()) == {"friendly", "hostile", "unknown"}
    assert abs(sum(probabilities.values()) - 1.0) < 1e-6
    assert probabilities["friendly"] == probabilities["hostile"] == probabilities["unknown"]


def test_identity_probabilities_use_context_when_stonesoup_available() -> None:
    bridge = StoneSoupBridge()
    bridge._stonesoup_available = True  # type: ignore[attr-defined]
    bridge.set_track_context(
        "TRK-HOSTILE",
        identity_hypotheses={"friendly": 0.1, "hostile": 0.8, "unknown": 0.1},
    )

    probabilities = bridge.get_identity_probabilities("TRK-HOSTILE")

    assert probabilities["hostile"] > probabilities["friendly"]
    assert abs(sum(probabilities.values()) - 1.0) < 1e-6


def test_association_confidence_clamps_to_probability_range() -> None:
    bridge = StoneSoupBridge()
    bridge.set_track_context("TRK-2", association_confidence=4.2)

    confidence = bridge.get_association_confidence("TRK-2")

    assert confidence == 1.0
