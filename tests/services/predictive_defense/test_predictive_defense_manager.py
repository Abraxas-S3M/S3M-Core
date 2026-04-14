"""Unit tests for predictive defense manager."""

from __future__ import annotations

from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager


def test_set_genome_context_creates_prediction_command_and_alert() -> None:
    manager = PredictiveDefenseManager()
    manager.set_genome_context(
        "trk-100",
        {"threat_score": 0.85, "confidence": 0.91, "predicted_intent": "attack", "horizon_seconds": 180},
    )

    predictions = manager.get_predictions()
    commands = manager.get_commands()
    alerts = manager.get_alerts()

    assert len(predictions) == 1
    assert predictions[0].track_id == "trk-100"
    assert predictions[0].predicted_intent == "attack"
    assert len(commands) == 1
    assert commands[0].action == "authorize_intercept_window"
    assert len(alerts) == 1
    assert alerts[0].posture.value == "high"
    assert alerts[0].severity == "high"


def test_swarm_analysis_returns_none_without_predictions() -> None:
    manager = PredictiveDefenseManager()
    assert manager.get_swarm_analysis() is None


def test_swarm_analysis_detects_group_pattern() -> None:
    manager = PredictiveDefenseManager()
    manager.set_genome_context("trk-1", {"threat_score": 0.7})
    manager.set_genome_context("trk-2", {"threat_score": 0.6})
    manager.set_genome_context("trk-3", {"threat_score": 0.8})

    swarm = manager.get_swarm_analysis()
    assert swarm is not None
    assert swarm.swarm_detected is True
    assert swarm.track_count == 3
    assert swarm.recommended_action == "activate_layered_intercept"


def test_invalid_track_id_raises_value_error() -> None:
    manager = PredictiveDefenseManager()

    try:
        manager.set_genome_context("   ", {"threat_score": 0.2})
    except ValueError as exc:
        assert "track_id required" in str(exc)
    else:
        raise AssertionError("expected ValueError")

