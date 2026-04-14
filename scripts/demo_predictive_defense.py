#!/usr/bin/env python3
"""Demonstrate S3M predictive defense — beyond-Krechet capability.

Scenario: 8 Shahed-class UAVs detected at 50km approaching ARAMCO facility.
Threat genome correlator identifies Houthi drone program signature.
Predictive engine forecasts convergence on facility in 10 minutes.
System pre-positions 5 Titan interceptors on predicted approach corridors
60 seconds before the swarm arrives.
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone
from src.sensor_fusion.models import Track, TrackState
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager


def main() -> None:
    print("=" * 72)
    print("S3M PREDICTIVE DEFENSE DEMO — BEYOND-KRECHET CAPABILITY")
    print("Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 72)

    defended = (0.0, 0.0, 0.0)
    mgr = PredictiveDefenseManager(
        defended_position=defended,
        outer_zone_radius_m=40000,
        interceptor_speed_mps=60,
    )

    # Step 1: Genome context (Houthi drone program profile)
    print("\n[1] Loading Houthi drone program genome context...")
    genome = {
        "actor_name": "Houthi Drone Program",
        "confidence": 0.75,
        "approach_bearing": 180,
        "speed_range_mps": [15, 25],
        "behavioral_pattern": "approach",
    }
    for i in range(8):
        mgr.set_genome_context(f"trk-shahed-{i:02d}", genome)
    print(f"  Genome context set for 8 tracks")

    # Step 2: Simulate radar tracks — 8 Shaheds approaching from south
    print("\n[2] RADAR: 8 Shahed-class UAVs detected at ~50km, heading north")
    tracks = []
    for i in range(8):
        track = Track(
            track_id=f"trk-shahed-{i:02d}",
            state=TrackState.CONFIRMED,
            position=(1000 * (i - 3.5), 50000 - i * 200, 800 + i * 20),
            velocity=(-2 + i * 0.3, -55 + i * 1.5, -1),
            covariance=[[1.0 if r == c else 0.0 for c in range(6)] for r in range(6)],
            last_update=datetime.now(timezone.utc),
            sensor_sources=["rps-202", "aesa-1"],
            classification="ENEMY_UAV",
            confidence=0.85,
        )
        tracks.append(track)

    # Step 3: Available interceptors
    interceptors = [
        {"interceptor_id": f"titan-{i+1}", "position": (400 * (i - 2), -800, 100)}
        for i in range(5)
    ]
    print(f"  Available interceptors: {len(interceptors)} Titan stations")

    # Step 4: Run predictive defense pipeline
    print("\n[3] Running predictive defense pipeline...")
    alert = mgr.process_tracks(tracks, interceptors)

    print(f"\n  ALERT: {alert.title_en}")
    print(f"  Severity: {alert.severity}")
    print(f"  Posture: {alert.posture.value}")
    print(f"  Threats: {alert.threat_count}")
    print(f"  Time to impact: {alert.time_to_impact_s:.0f}s")

    print(f"\n  Recommended actions:")
    for action in alert.recommended_actions:
        print(f"    - {action}")

    # Step 5: Show predictions
    print(f"\n[4] Trajectory predictions:")
    for pred in mgr.get_predictions()[:4]:
        print(
            f"  {pred.track_id}: "
            f"range={pred.range_to_asset_now_m:.0f}m "
            f"arrival={pred.time_to_asset_s:.0f}s "
            f"genome={'YES' if pred.genome_bias_applied else 'no'} "
            f"conf={pred.prediction_confidence:.2f}"
        )

    # Step 6: Swarm analysis
    swarm = mgr.get_swarm_analysis()
    if swarm:
        print(f"\n[5] Swarm analysis:")
        print(f"  Tracks: {swarm.track_count}")
        print(f"  Intent: {swarm.intent.value}")
        print(f"  Convergence in: {swarm.convergence_time_s:.0f}s")
        print(f"  Approach bearing: {swarm.approach_bearing_deg:.0f}°")
        print(f"  Effectors needed: {swarm.effectors_required}")
        print(f"  Estimated defense Pk: {swarm.estimated_pk_defense:.2f}")

    # Step 7: Pre-position commands
    print(f"\n[6] Pre-position commands:")
    for cmd in mgr.get_commands():
        print(
            f"  {cmd.interceptor_id} -> ({cmd.intercept_position[0]:.0f}, "
            f"{cmd.intercept_position[1]:.0f}, {cmd.intercept_position[2]:.0f}) "
            f"{'LAUNCH NOW' if cmd.launch_now else f'launch in {cmd.launch_time_offset_s:.0f}s'} "
            f"window={cmd.engagement_window_s:.0f}s conf={cmd.confidence:.2f}"
        )

    print(f"\n{'=' * 72}")
    stats = mgr.get_stats()
    print(f"PREDICTIVE DEFENSE STATUS")
    print(f"  Active predictions: {stats['active_predictions']}")
    print(f"  Swarm detected: {stats['swarm_detected']}")
    print(f"  Pre-position commands: {stats['pre_position_commands']}")
    print(f"  Genome contexts: {stats['genome_contexts_cached']}")
    print(f"{'=' * 72}")
    print("Demo complete. Predictive defense engine operational.")
    print("S3M now operates 60-120s ahead of any reactive C2 system.")


if __name__ == "__main__":
    main()
