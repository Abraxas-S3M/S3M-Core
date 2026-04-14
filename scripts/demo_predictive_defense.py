#!/usr/bin/env python3
"""End-to-end demo for the S3M Predictive Threat Trajectory Engine.

Scenario:
- Shahed swarm detected at 50 km
- Genome match identifies Houthi behavioral pattern
- System forecasts convergence on ARAMCO facility
- Five Titan interceptors are pre-positioned before swarm ingress
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, ".")

from services.predictive_defense.preposition_optimizer import InterceptorProfile
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager
from src.threat_genome.genome_store import ThreatGenomeStore
from src.threat_genome.models import BehavioralSignature, SignatureType, ThreatGenome


@dataclass
class DemoTrack:
    track_id: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    classification: str
    confidence: float = 0.85
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DemoTargetAllocator:
    def __init__(self) -> None:
        self.allocations: List[Dict[str, Any]] = []

    def allocate(
        self,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
    ) -> Dict[str, Any]:
        row = {
            "allocated": True,
            "target_id": target_id,
            "target_position": [round(v, 1) for v in target_position],
            "target_speed_mps": round(target_speed_mps, 2),
            "target_classification": target_classification,
            "effector_id": f"titan-slot-{(len(self.allocations) % 5) + 1}",
        }
        self.allocations.append(row)
        return row


class DemoInterceptorManager:
    def __init__(self) -> None:
        self.actions: List[Dict[str, Any]] = []

    def assign_target(self, interceptor_id: str, target_id: str) -> bool:
        self.actions.append({"action": "assign_target", "interceptor_id": interceptor_id, "target_id": target_id})
        return True

    def launch(self, interceptor_id: str) -> bool:
        self.actions.append({"action": "launch", "interceptor_id": interceptor_id})
        return True


def _seed_houthi_genome(store: ThreatGenomeStore) -> None:
    genome = ThreatGenome(
        actor_name="Houthi Shahed Program",
        actor_type="uav",
        confidence=0.86,
        regions={"yemen", "red_sea"},
        tags={"uav", "strike_run", "southern_approach"},
        threat_rating="high",
    )
    movement_sig = BehavioralSignature(
        name="houthi_shahed_movement",
        signature_type=SignatureType.MOVEMENT,
        movement_patterns={
            "heading_deg": [170, 190],
            "speed_mps": [15, 25],
        },
        confidence=0.92,
    )
    temporal_sig = BehavioralSignature(
        name="houthi_dawn_window",
        signature_type=SignatureType.TEMPORAL,
        temporal_patterns={
            "hour_utc": [4, 8],
        },
        confidence=0.88,
    )
    genome.add_signature(movement_sig)
    genome.add_signature(temporal_sig)
    store.add_genome(genome)


def _shahed_swarm_tracks() -> List[DemoTrack]:
    tracks: List[DemoTrack] = []
    for index in range(10):
        lateral_offset = random.uniform(-1500.0, 1500.0)
        altitude = random.uniform(90.0, 170.0)
        track = DemoTrack(
            track_id=f"shahed-{index+1:02d}",
            position=(50_000.0 + random.uniform(-500.0, 500.0), lateral_offset, altitude),
            velocity=(-20.0 + random.uniform(-1.5, 1.5), random.uniform(-0.5, 0.5), 0.0),
            classification="ENEMY_UAV",
            metadata={
                "threat_level": "high",
                "regions": ["red_sea"],
                "behavior_tags": ["uav", "swarm", "strike_run"],
            },
        )
        tracks.append(track)
    return tracks


def _interceptor_profiles() -> List[InterceptorProfile]:
    # Tactical context: interceptors are already airborne in a forward CAP lane.
    return [
        InterceptorProfile("titan-01", (43_000.0, -1_200.0, 250.0), 90.0, 1.0),
        InterceptorProfile("titan-02", (43_000.0, 1_200.0, 250.0), 90.0, 1.0),
        InterceptorProfile("titan-03", (42_000.0, -2_400.0, 250.0), 92.0, 1.0),
        InterceptorProfile("titan-04", (42_000.0, 2_400.0, 250.0), 92.0, 1.0),
        InterceptorProfile("titan-05", (41_500.0, 0.0, 250.0), 95.0, 1.0),
    ]


def main() -> None:
    random.seed(905)
    store = ThreatGenomeStore()
    _seed_houthi_genome(store)
    allocator = DemoTargetAllocator()
    interceptor_manager = DemoInterceptorManager()
    manager = PredictiveDefenseManager(
        target_allocator=allocator,
        interceptor_manager=interceptor_manager,
        defended_asset_position_m=(0.0, 0.0, 0.0),
        defended_asset_name_en="ARAMCO Facility",
        defended_asset_name_ar="منشأة أرامكو",
        genome_store=store,
    )
    manager.configure_interceptors(_interceptor_profiles())

    posture = manager.process_cycle(tracks=_shahed_swarm_tracks())

    print("=== S3M Predictive Threat Trajectory Engine Demo ===")
    print("Scenario: Shahed swarm detected at 50 km from ARAMCO facility.")
    if posture.trajectory_predictions:
        genome_name = posture.trajectory_predictions[0].matched_genome_name or "unknown genome"
        print(f"Genome correlation: matched to {genome_name}.")
    if posture.swarm_predictions:
        swarm = posture.swarm_predictions[0]
        print(
            f"Swarm forecast: convergence point {tuple(round(v, 1) for v in swarm.convergence_point_m)} "
            f"ETA {swarm.eta_to_asset_s:.1f}s intent={swarm.intent_classification}."
        )

    print(f"Defense posture: {posture.posture_level}")
    print(f"Pre-position commands issued: {len(posture.preposition_commands)}")
    for command in posture.preposition_commands[:5]:
        delta_s = command.intercept_time_s - command.launch_time_s
        print(
            f"  {command.interceptor_id} -> {command.target_track_id} "
            f"intercept in {delta_s:.1f}s at {tuple(round(v, 1) for v in command.intercept_point_m)}"
        )

    print(f"Allocator cues: {len(posture.allocator_outcomes)}")
    print(f"Interceptor actions: {len(posture.interceptor_actions)}")
    print("Result: Titan interceptors were pre-positioned on predictive trajectories before swarm ingress.")


if __name__ == "__main__":
    main()
