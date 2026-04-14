"""Unit tests for predictive defense orchestration and core components."""

from __future__ import annotations

from datetime import datetime, timezone

from services.predictive_defense.models import DefensePosture, ThreatTrajectoryPrediction
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager
from services.predictive_defense.preposition_optimizer import PrePositionOptimizer
from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from src.sensor_fusion.models import Track, TrackState


def _track(
    *,
    track_id: str,
    state: TrackState = TrackState.CONFIRMED,
    position: tuple[float, float, float] = (1000.0, 0.0, 100.0),
    velocity: tuple[float, float, float] = (-40.0, 0.0, 0.0),
    classification: str = "ENEMY_UAV",
) -> Track:
    return Track(
        track_id=track_id,
        state=state,
        position=position,
        velocity=velocity,
        covariance=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        last_update=datetime.now(timezone.utc),
        sensor_sources=["radar-1"],
        classification=classification,
        confidence=0.85,
        history=[
            {
                "position": (position[0] + 80.0, position[1], position[2]),
                "velocity": velocity,
                "classification": classification,
            },
            {
                "position": (position[0] + 40.0, position[1], position[2]),
                "velocity": velocity,
                "classification": classification,
            },
        ],
    )


def test_track_bridge_creates_entity_snapshot() -> None:
    bridge = TrackGenomeBridge()
    entity = bridge.track_to_entity_snapshot(_track(track_id="trk-bridge"))
    assert entity.entity_id == "trk-bridge"
    assert entity.entity_type == "uav"
    assert entity.threat_level == "high"
    assert entity.history_depth == 2
    assert entity.speed_mps > 0.0


def test_manager_returns_low_alert_when_no_confirmed_tracks() -> None:
    manager = PredictiveDefenseManager()
    alert = manager.process_tracks([_track(track_id="trk-1", state=TrackState.TENTATIVE)])
    assert alert.severity == "low"
    assert alert.posture == DefensePosture.NORMAL
    assert alert.threat_count == 0
    assert manager.get_predictions() == []
    assert manager.get_commands() == []


def test_manager_generates_commands_and_genome_actions() -> None:
    manager = PredictiveDefenseManager(defended_position=(0.0, 0.0, 0.0), outer_zone_radius_m=40000.0)
    manager.set_genome_context("trk-2", {"match_name": "wolfpack-alpha"})
    alert = manager.process_tracks(
        [_track(track_id="trk-2", position=(1200.0, 200.0, 120.0), velocity=(-60.0, -5.0, 0.0))],
        available_interceptors=[{"interceptor_id": "int-1", "position": (0.0, 0.0, 0.0), "ready": True}],
    )

    assert alert.threat_count == 1
    assert alert.posture in {DefensePosture.IMMINENT, DefensePosture.PRE_POSITION, DefensePosture.ELEVATED}
    assert any("Genome match: wolfpack-alpha" in action for action in alert.recommended_actions)
    assert len(alert.pre_position_commands) == 1
    assert manager.get_stats()["pre_position_commands"] == 1


def test_manager_detects_swarm_for_multiple_tracks() -> None:
    manager = PredictiveDefenseManager(defended_position=(0.0, 0.0, 0.0))
    alert = manager.process_tracks(
        [
            _track(track_id="trk-a", position=(2400.0, 0.0, 100.0), velocity=(-55.0, 0.0, 0.0)),
            _track(track_id="trk-b", position=(2600.0, 100.0, 100.0), velocity=(-55.0, -2.0, 0.0)),
            _track(track_id="trk-c", position=(2500.0, -100.0, 120.0), velocity=(-55.0, 2.0, 0.0)),
        ],
        available_interceptors=[
            {"interceptor_id": "int-a", "position": (0.0, 0.0, 0.0), "ready": True},
            {"interceptor_id": "int-b", "position": (100.0, 0.0, 0.0), "ready": True},
        ],
    )
    swarm = manager.get_swarm_analysis()
    assert swarm is not None
    assert swarm.track_count == 3
    assert any(action.startswith("Swarm detected:") for action in alert.recommended_actions)


def test_optimizer_ignores_unready_interceptors() -> None:
    optimizer = PrePositionOptimizer(interceptor_speed_mps=50.0, defended_position=(0.0, 0.0, 0.0))
    commands = optimizer.optimize_preposition(
        predictions=[
            ThreatTrajectoryPrediction(
                track_id="trk-opt",
                predicted_position=(1000.0, 0.0, 100.0),
                time_to_asset_s=45.0,
                distance_to_asset_m=1000.0,
                approach_speed_mps=20.0,
                confidence=0.7,
                risk_score=0.6,
            )
        ],
        interceptors=[
            {"interceptor_id": "int-offline", "position": (0.0, 0.0, 0.0), "ready": False},
            {"interceptor_id": "int-ready", "position": (0.0, 0.0, 0.0), "ready": True},
        ],
    )
    assert len(commands) == 1
    assert commands[0].interceptor_id == "int-ready"
