#!/usr/bin/env python3
"""Demonstrate S3M multi-radar air picture — Krechet-equivalent integration.

Simulates:
1. Deploy Krechet radar suite (RPS-82 + RPS-202 + AESA)
2. Incoming Shahed-class UAV detected at 45km by AESA
3. Same target detected at 18km by RPS-202
4. Same target detected at 12km by RPS-82
5. Multi-radar fused track with RCS classification
"""

import sys

sys.path.insert(0, ".")

from services.radar.krechet_radar_suite import create_krechet_radar_suite
from services.radar.radar_manager import RadarManager


def main() -> None:
    print("=" * 70)
    print("S3M RADAR INTEGRATION DEMO — KRECHET MULTI-RADAR AIR PICTURE")
    print("Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 70)

    mgr = RadarManager()
    print("\n[1] Deploying Krechet radar suite...")
    configs = create_krechet_radar_suite(mgr, center=(0, 0, 0))
    for c in configs:
        print(f"  {c.name_en} ({c.radar_type.value}) — max range {c.max_range_m / 1000:.0f}km")

    # Tactical context: long-range AESA gives early warning for layered defense cueing.
    print("\n[2] AESA detects target at 45km (Shahed-class UAV, RCS ~ -10 dBsm)")
    aesa_id = configs[2].radar_id
    plots = mgr.ingest_scan(
        aesa_id,
        {
            "plots": [
                {
                    "range_m": 45000,
                    "azimuth_deg": 10,
                    "elevation_deg": 2,
                    "velocity_mps": 55,
                    "rcs_dbsm": -10,
                    "snr_db": 22,
                },
            ]
        },
    )
    for p in plots:
        print(
            f"  Plot: range={p.range_m}m az={p.azimuth_deg}° "
            f"class={p.rcs_classification.value} conf={p.classification_confidence:.2f}"
        )
        print(
            "  Cartesian: "
            f"({p.position_cartesian[0]:.0f}, {p.position_cartesian[1]:.0f}, {p.position_cartesian[2]:.0f})"
        )

    print("\n[3] RPS-202 detects same target at 18km")
    rps202_id = configs[1].radar_id
    plots2 = mgr.ingest_scan(
        rps202_id,
        {
            "plots": [
                {
                    "range_m": 18000,
                    "azimuth_deg": 12,
                    "elevation_deg": 3,
                    "velocity_mps": 58,
                    "rcs_dbsm": -9,
                    "snr_db": 20,
                },
            ]
        },
    )
    for p in plots2:
        print(f"  Plot: range={p.range_m}m az={p.azimuth_deg}° class={p.rcs_classification.value}")

    print("\n[4] RPS-82 detects same target at 12km")
    rps82_id = configs[0].radar_id
    plots3 = mgr.ingest_scan(
        rps82_id,
        {
            "plots": [
                {
                    "range_m": 12000,
                    "azimuth_deg": 14,
                    "elevation_deg": 4,
                    "velocity_mps": 60,
                    "rcs_dbsm": -8,
                    "snr_db": 18,
                },
            ]
        },
    )
    for p in plots3:
        print(f"  Plot: range={p.range_m}m az={p.azimuth_deg}° class={p.rcs_classification.value}")

    print("\n[5] Fusing multi-radar tracks...")
    tracks = mgr.process_fused_tracks()
    print(f"  Fused tracks: {len(tracks)}")
    for t in tracks:
        print(f"  Track {t.track_id[:8]} state={t.state.value} class={t.classification}")
        print(f"    pos=({t.position[0]:.0f}, {t.position[1]:.0f}, {t.position[2]:.0f})")
        print(f"    vel=({t.velocity[0]:.1f}, {t.velocity[1]:.1f}, {t.velocity[2]:.1f}) m/s")
        print(f"    sensors: {t.sensor_sources}")

    print("\n" + "=" * 70)
    print("RADAR STATUS")
    for rid, status in mgr.get_all_status().items():
        r = mgr.get_radar(rid)
        if r is None:
            continue
        print(f"  {r.name_en}: {status['scans']} scans, {status['plots']} plots, {status['correlated']} correlated")
    print("=" * 70)
    print("Demo complete. Multi-radar air picture operational.")


if __name__ == "__main__":
    main()
