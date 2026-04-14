"""Unit tests for predictive defense trajectory-to-action pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from services.predictive_defense.preposition_optimizer import InterceptorProfile, PrePositionOptimizer
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager
from services.predictive_defense.swarm_analyzer import SwarmAnalyzer
from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from services.predictive_defense.trajectory_predictor import GenomeAwareTrajectoryPredictor
from src.threat_genome.genome_store import ThreatGenomeStore
from src.threat_genome.models import BehavioralSignature, SignatureType, ThreatGenome


@dataclass
class _Track:
    track_id: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    classification: str = "ENEMY_UAV"
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class _Allocator:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def allocate(
        self,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
    ) -> Dict[str, Any]:
        payload = {
            "allocated": True,
            "target_id": target_id,
            "target_position": target_position,
            "target_speed_mps": target_speed_mps,
            "target_classification": target_classification,
        }
        self.calls.append(payload)
        return payload


class _InterceptorManager:
    def __init__(self) -> None:
        self.actions: List[Dict[str, Any]] = []

    def assign_target(self, interceptor_id: str, target_id: str) -> bool:
        self.actions.append({"action": "assign_target", "interceptor_id": interceptor_id, "target_id": target_id})
        return True

    def launch(self, interceptor_id: str) -> bool:
        self.actions.append({"action": "launch", "interceptor_id": interceptor_id})
        return True


def _houthi_genome() -> ThreatGenome:
    genome = ThreatGenome(
        actor_name="Houthi Drone Program",
        actor_type="uav",
        confidence=0.9,
        regions={"red_sea"},
        tags={"uav", "strike_run"},
        threat_rating="high",
    )
    genome.add_signature(
        BehavioralSignature(
            name="movement",
            signature_type=SignatureType.MOVEMENT,
            movement_patterns={"heading_deg": [170, 190], "speed_mps": [15, 25]},
            confidence=0.95,
        )
    )
    genome.add_signature(
        BehavioralSignature(
            name="temporal",
            signature_type=SignatureType.TEMPORAL,
            temporal_patterns={"hour_utc": [0, 23]},
            confidence=0.85,
        )
    )
    return genome


def test_track_genome_bridge_builds_snapshot_and_history() -> None:
    bridge = TrackGenomeBridge(history_limit=5)
    track = _Track(
        track_id="trk-1",
        position=(1_000.0, 200.0, 120.0),
        velocity=(-20.0, 0.0, 0.0),
        metadata={"threat_level": "high", "regions": ["red_sea"]},
    )
    first = bridge.to_context(track)
    second = bridge.to_context(track)

    assert first.entity_snapshot.entity_id == "trk-1"
    assert second.entity_snapshot.history_depth == 2
    assert second.genome_observation.classification == "ENEMY_UAV"
    assert "uav" in second.entity_snapshot.behavior_tags


def test_genome_aware_trajectory_predictor_uses_genome_bias() -> None:
    bridge = TrackGenomeBridge()
    track = _Track(
        track_id="trk-2",
        position=(5_000.0, 0.0, 130.0),
        velocity=(-20.0, 0.0, 0.0),
        metadata={"threat_level": "high", "regions": ["red_sea"]},
    )
    context = bridge.to_context(track)
    predictor = GenomeAwareTrajectoryPredictor()
    prediction = predictor.predict(context=context, matched_genome=_houthi_genome())

    assert prediction.matched_genome_name == "Houthi Drone Program"
    assert prediction.predicted_positions_m
    assert 60 in prediction.predicted_positions_m
    assert prediction.forecast_confidence > 0.0
    assert prediction.risk_score > 0.0


def test_swarm_analyzer_classifies_saturation_attack() -> None:
    from services.predictive_defense.models import ThreatTrajectoryPrediction

    predictions: List[ThreatTrajectoryPrediction] = []
    for idx in range(8):
        predictions.append(
            ThreatTrajectoryPrediction(
                track_id=f"sw-{idx}",
                predicted_positions_m={60: (1_000.0 + idx * 150.0, idx * 80.0, 100.0)},
                predicted_speeds_mps={60: 22.0},
                risk_score=0.8,
                forecast_confidence=0.85,
            )
        )
    analyzer = SwarmAnalyzer(min_swarm_size=3, cluster_distance_m=2_500.0, saturation_threshold=6)
    swarms = analyzer.analyze(
        trajectory_predictions=predictions,
        defended_asset_position_m=(0.0, 0.0, 0.0),
        defended_asset_name_en="Asset",
        defended_asset_name_ar="أصل",
    )

    assert swarms
    assert swarms[0].intent_classification == "saturation attack"
    assert swarms[0].threat_count >= 6


def test_preposition_optimizer_generates_command() -> None:
    from services.predictive_defense.models import ThreatTrajectoryPrediction

    prediction = ThreatTrajectoryPrediction(
        track_id="target-1",
        predicted_positions_m={60: (2_000.0, 0.0, 100.0)},
        predicted_speeds_mps={60: 20.0},
        forecast_confidence=0.9,
        risk_score=0.88,
    )
    optimizer = PrePositionOptimizer(arrival_buffer_s=5.0)
    commands = optimizer.optimize(
        trajectory_predictions=[prediction],
        interceptor_profiles=[
            InterceptorProfile("int-1", (1_600.0, 0.0, 100.0), 90.0, 1.0),
            InterceptorProfile("int-2", (100.0, 0.0, 100.0), 80.0, 1.0),
        ],
        now_s=1_000.0,
    )

    assert len(commands) == 1
    assert commands[0].interceptor_id == "int-1"
    assert commands[0].target_track_id == "target-1"


def test_predictive_defense_manager_pipeline_end_to_end() -> None:
    store = ThreatGenomeStore()
    store.add_genome(_houthi_genome())
    allocator = _Allocator()
    interceptor_manager = _InterceptorManager()
    manager = PredictiveDefenseManager(
        target_allocator=allocator,
        interceptor_manager=interceptor_manager,
        defended_asset_position_m=(0.0, 0.0, 0.0),
        defended_asset_name_en="ARAMCO",
        defended_asset_name_ar="أرامكو",
        genome_store=store,
    )
    manager.configure_interceptors(
        [
            InterceptorProfile("titan-01", (1_500.0, -500.0, 100.0), 100.0, 1.0),
            InterceptorProfile("titan-02", (1_500.0, 500.0, 100.0), 100.0, 1.0),
            InterceptorProfile("titan-03", (1_400.0, 0.0, 100.0), 100.0, 1.0),
        ]
    )

    tracks = [
        _Track(
            track_id=f"swarm-{idx}",
            position=(2_000.0 + idx * 50.0, idx * 80.0, 120.0),
            velocity=(-20.0, 0.0, 0.0),
            metadata={"threat_level": "high", "regions": ["red_sea"], "behavior_tags": ["swarm"]},
        )
        for idx in range(6)
    ]
    posture = manager.process_cycle(tracks=tracks, now_s=10_000.0)

    assert posture.trajectory_predictions
    assert posture.swarm_predictions
    assert posture.preposition_commands
    assert posture.allocator_outcomes
    assert posture.interceptor_actions
    assert posture.posture_level in {"elevated", "critical"}
    payload = posture.to_dict()
    assert payload["name_ar"] == "وضعية الدفاع التنبؤي"
