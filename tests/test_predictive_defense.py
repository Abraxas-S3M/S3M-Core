"""Tests for S3M predictive threat trajectory engine."""

import sys
import math
sys.path.insert(0, ".")

from src.sensor_fusion.models import Track, TrackState
from src.prediction.prediction_models import EntitySnapshot, HistoricalObservation
from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from services.predictive_defense.trajectory_predictor import TrajectoryPredictor
from services.predictive_defense.swarm_analyzer import SwarmAnalyzer
from services.predictive_defense.preposition_optimizer import PrePositionOptimizer
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager
from services.predictive_defense.models import DefensePosture, SwarmIntent
from datetime import datetime, timezone


def _make_track(track_id, x, y, z, vx, vy, classification="ENEMY_UAV"):
    return Track(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        position=(x, y, z),
        velocity=(vx, vy, 0.0),
        covariance=[[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)],
        last_update=datetime.now(timezone.utc),
        sensor_sources=["radar-1"],
        classification=classification,
        confidence=0.85,
    )


# --- Bridge Tests ---

def test_bridge_converts_track_to_entity():
    bridge = TrackGenomeBridge()
    track = _make_track("trk-1", 20000, 30000, 800, -10, -40)
    entity = bridge.track_to_entity_snapshot(track)
    assert entity.entity_id == "trk-1"
    assert entity.speed_mps > 0
    assert entity.threat_level == "high"


# --- Trajectory Predictor Tests ---

def test_predictor_produces_positions():
    predictor = TrajectoryPredictor(defended_position=(0, 0, 0))
    entity = EntitySnapshot(
        entity_id="e1", entity_type="ENEMY_UAV",
        position=(30000, 0, 800), speed_mps=50, heading_deg=180,
        threat_level="high", confidence=0.8,
        history=[
            HistoricalObservation(timestamp_s=i, position=(30000+50*i, 0, 800), speed_mps=50, heading_deg=180)
            for i in range(5)
        ],
    )
    pred = predictor.predict(entity)
    assert pred.predicted_30s is not None
    assert pred.predicted_60s is not None
    assert pred.range_to_asset_now_m > 0
    assert pred.time_to_asset_s > 0


def test_predictor_with_genome_bias():
    predictor = TrajectoryPredictor(defended_position=(0, 0, 0))
    entity = EntitySnapshot(
        entity_id="e2", entity_type="ENEMY_UAV",
        position=(30000, 0, 800), speed_mps=50, heading_deg=180,
        threat_level="high", confidence=0.8,
        history=[HistoricalObservation(timestamp_s=i, position=(30000+50*i, 0, 800), speed_mps=50, heading_deg=180) for i in range(5)],
    )
    genome_ctx = {
        "actor_name": "Houthi Drone Program",
        "confidence": 0.75,
        "approach_bearing": 175,
        "speed_range_mps": [15, 25],
        "behavioral_pattern": "approach",
    }
    pred = predictor.predict(entity, genome_ctx)
    assert pred.genome_bias_applied is True
    assert pred.genome_match == "Houthi Drone Program"


# --- Swarm Analyzer Tests ---

def test_swarm_detection():
    preds = []
    for i in range(8):
        from services.predictive_defense.models import ThreatTrajectoryPrediction
        preds.append(ThreatTrajectoryPrediction(
            track_id=f"trk-{i}",
            current_position=(30000 + i*100, 500 * i, 800),
            current_speed_mps=50 + i,
            current_heading_deg=180 + i * 2,
            predicted_60s=(15000 + i*50, 250*i, 800),
            time_to_asset_s=300 - i * 10,
        ))
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    swarm = analyzer.analyze(preds, (0, 0, 0))
    assert swarm is not None
    assert swarm.track_count == 8
    assert swarm.intent in {SwarmIntent.SATURATION, SwarmIntent.UNKNOWN, SwarmIntent.SEQUENTIAL}


def test_no_swarm_below_threshold():
    from services.predictive_defense.models import ThreatTrajectoryPrediction
    preds = [ThreatTrajectoryPrediction(track_id="solo", current_position=(30000, 0, 800))]
    analyzer = SwarmAnalyzer(min_swarm_size=3)
    assert analyzer.analyze(preds, (0, 0, 0)) is None


# --- Pre-Position Optimizer Tests ---

def test_optimizer_produces_commands():
    from services.predictive_defense.models import ThreatTrajectoryPrediction
    pred = ThreatTrajectoryPrediction(
        track_id="trk-1",
        current_position=(30000, 0, 800), current_speed_mps=50,
        current_heading_deg=180,
        predicted_30s=(28500, 0, 800), predicted_60s=(27000, 0, 800),
        time_to_asset_s=600,
    )
    opt = PrePositionOptimizer(interceptor_speed_mps=60, defended_position=(0, 0, 0))
    cmds = opt.optimize_preposition(
        [pred],
        [{"interceptor_id": "intc-1", "position": (0, 0, 100)}],
    )
    assert len(cmds) == 1
    assert cmds[0].interceptor_id == "intc-1"
    assert cmds[0].intercept_position[0] > 0  # Ahead of defended position


# --- Full Pipeline Test ---

def test_full_pipeline():
    mgr = PredictiveDefenseManager(defended_position=(0, 0, 0))
    mgr.set_genome_context("trk-1", {
        "actor_name": "Houthi Drone Program",
        "confidence": 0.75,
        "approach_bearing": 180,
        "speed_range_mps": [15, 25],
        "behavioral_pattern": "approach",
    })

    tracks = [
        _make_track("trk-1", 35000, 1000, 800, -5, -50),
        _make_track("trk-2", 34000, -500, 750, -3, -48),
        _make_track("trk-3", 36000, 2000, 820, -4, -52),
    ]

    interceptors = [
        {"interceptor_id": "titan-1", "position": (0, -500, 100)},
        {"interceptor_id": "titan-2", "position": (500, 0, 100)},
        {"interceptor_id": "titan-3", "position": (-500, 500, 100)},
    ]

    alert = mgr.process_tracks(tracks, interceptors)
    assert alert.threat_count == 3
    assert alert.posture in {DefensePosture.ELEVATED, DefensePosture.PRE_POSITION, DefensePosture.IMMINENT}
    assert len(alert.pre_position_commands) >= 1

    preds = mgr.get_predictions()
    assert len(preds) == 3
    assert preds[0].genome_match == "Houthi Drone Program"

    stats = mgr.get_stats()
    assert stats["active_predictions"] == 3


if __name__ == "__main__":
    test_bridge_converts_track_to_entity()
    test_predictor_produces_positions()
    test_predictor_with_genome_bias()
    test_swarm_detection()
    test_no_swarm_below_threshold()
    test_optimizer_produces_commands()
    test_full_pipeline()
    print("ALL PREDICTIVE DEFENSE TESTS PASSED")
