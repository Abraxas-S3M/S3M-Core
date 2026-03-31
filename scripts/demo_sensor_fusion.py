#!/usr/bin/env python3
"""Demonstrate S3M Phase 5 sensor fusion pipeline."""

import sys

sys.path.insert(0, ".")

from src.sensor_fusion.sensor_manager import SensorManager


def main() -> None:
    print("=" * 68)
    print("S3M PHASE 5 SENSOR FUSION DEMO")
    print("Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 68)

    manager = SensorManager()
    manager.register_sensor("eo_cam_1", "EO_CAMERA", {"sector": "NORTH"})
    manager.register_sensor("radar_1", "RADAR", {"range_km": 25})
    manager.register_sensor("lidar_1", "LIDAR", {"resolution": "high"})

    print("\nRegistered sensors:")
    for sensor in manager.get_sensors():
        print(f"  - {sensor['sensor_id']} [{sensor['sensor_type']}]")

    print("\nIngesting simulated moving target readings...")
    positions = [
        (1000.0, 500.0, 20.0),
        (1010.0, 505.0, 20.0),
        (1020.0, 510.0, 20.0),
    ]
    for step, pos in enumerate(positions, start=1):
        manager.ingest("eo_cam_1", {"classification": "tank", "step": step}, position=pos, confidence=0.82)
        manager.ingest("radar_1", {"classification": "tank", "step": step}, position=(pos[0] + 2, pos[1] - 1, pos[2]), confidence=0.88)
        manager.ingest("lidar_1", {"classification": "tank", "step": step}, position=(pos[0] - 1, pos[1] + 1, pos[2]), confidence=0.86)
        tracks = manager.process()
        print(f"  Step {step}: {len(tracks)} active track(s)")
        for track in tracks:
            print(
                f"    {track.track_id[:8]} state={track.state.value} "
                f"pos={tuple(round(v, 2) for v in track.position)} "
                f"vel={tuple(round(v, 2) for v in track.velocity)} "
                f"class={track.classification}"
            )

    print("\nConverting confirmed tracks to threat events...")
    events = manager.to_threat_events()
    print(f"Generated {len(events)} threat event(s).")
    for event in events:
        print(f"  - [{event.level.name}/{event.category.value}] {event.title}")

    print("\nSensor fusion demo complete.")


if __name__ == "__main__":
    main()
