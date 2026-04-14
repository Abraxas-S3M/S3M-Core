"""Demo: multi-radar integration into one fused tactical picture.

Military context:
This script emulates a command-post exercise where heterogeneous radars report
simultaneously and feed Layer 02 fusion with normalized tactical contacts.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pprint import pprint

# Ensure script works when executed directly from repository root or scripts/ path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.radar.krechet_radar_suite import load_krechet_suite
from services.radar.radar_manager import RadarManager


def _build_demo_scan(ts: datetime):
    return {
        "timestamp": ts.isoformat(),
        "scan_mode": "TRACK_WHILE_SCAN",
        "plots": [
            {
                "plot_id": "demo-fast-uav",
                "range_m": 12_500.0,
                "azimuth_deg": 35.0,
                "elevation_deg": 2.0,
                "radial_velocity_mps": 70.0,
                "rcs_m2": 0.04,
                "snr_db": 16.0,
            },
            {
                "plot_id": "demo-cruise",
                "range_m": 28_000.0,
                "azimuth_deg": 102.0,
                "elevation_deg": 4.0,
                "radial_velocity_mps": 230.0,
                "rcs_m2": 0.35,
                "snr_db": 18.0,
            },
            {
                "plot_id": "demo-large-aircraft",
                "range_m": 54_000.0,
                "azimuth_deg": 280.0,
                "elevation_deg": 6.0,
                "radial_velocity_mps": 145.0,
                "rcs_m2": 22.0,
                "snr_db": 20.0,
            },
        ],
    }


def run_demo() -> None:
    manager = RadarManager()
    suite = load_krechet_suite(manager)
    print(f"Loaded suite '{suite.suite_name}' with {len(suite.radar_configs)} radars")

    timestamp = datetime.now(timezone.utc)
    radar_ids = ["rps82-alpha", "rps202-bravo", "western-aesa-charlie"]
    for radar_id in radar_ids:
        raw_scan = _build_demo_scan(timestamp)
        readings, correlations = manager.ingest_scan_with_correlations(radar_id, raw_scan)
        print(f"\nRadar {radar_id}: {len(readings)} readings, {len(correlations)} correlations")
        for reading in readings:
            print(
                f"  plot={reading.data.get('plot_id')} "
                f"class={reading.data.get('classification')} "
                f"alloc={reading.data.get('target_allocator_classification')} "
                f"pos={reading.position}"
            )

    tracks = manager.process_fusion()
    print(f"\nFused track count: {len(tracks)}")
    for track in tracks:
        pprint(track.to_dict())


if __name__ == "__main__":
    run_demo()
