#!/usr/bin/env python3
"""S3M Phase 15 full maritime surveillance demo pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from random import Random
from typing import Dict, List

from services.sensor_analytics import SARDetection, SensorAnalyticsManager, VesselClassification


def _write_sample_ais_csv(filepath: str) -> None:
    rng = Random(42)
    now = datetime.now(timezone.utc)
    classifications = (
        [VesselClassification.CARGO] * 5
        + [VesselClassification.TANKER] * 3
        + [VesselClassification.FISHING] * 4
        + [VesselClassification.MILITARY_SURFACE] * 3
        + [VesselClassification.PATROL] * 2
        + [VesselClassification.UNKNOWN] * 3
    )
    rows: List[Dict[str, object]] = []
    for idx, cls in enumerate(classifications):
        mmsi = f"966000{idx:03d}"
        base_lat = 26.0 + rng.uniform(-0.5, 0.5)
        base_lon = 50.0 + rng.uniform(-0.5, 0.5)
        vessel_type = {
            VesselClassification.CARGO: 70,
            VesselClassification.TANKER: 80,
            VesselClassification.FISHING: 30,
            VesselClassification.MILITARY_SURFACE: 55,
            VesselClassification.PATROL: 50,
            VesselClassification.UNKNOWN: 0,
        }[cls]
        for step in range(4):
            ts = now - timedelta(minutes=30 * (3 - step))
            lat = base_lat + step * 0.01
            lon = base_lon + step * 0.01
            speed = 10 + rng.uniform(-2, 4)
            rows.append(
                {
                    "MMSI": mmsi,
                    "timestamp": ts.isoformat(),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "speed": round(speed, 2),
                    "course": round(45 + rng.uniform(-10, 10), 2),
                    "heading": round(45 + rng.uniform(-10, 10), 2),
                    "vessel_name": f"DEMO-{idx:02d}",
                    "vessel_type": vessel_type,
                    "destination": "Jubail",
                    "nav_status": 0,
                    "message_type": 1,
                }
            )
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    headers = [
        "MMSI",
        "timestamp",
        "lat",
        "lon",
        "speed",
        "course",
        "heading",
        "vessel_name",
        "vessel_type",
        "destination",
        "nav_status",
        "message_type",
    ]
    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            handle.write(",".join(str(row[h]) for h in headers) + "\n")


def main() -> None:
    manager = SensorAnalyticsManager()
    ais_path = "data/ais/demo_maritime_tracks.csv"
    _write_sample_ais_csv(ais_path)

    ingest = manager.ingest_ais(ais_path)
    print(f"[1] AIS ingested: {ingest}")

    # Simulate 2 dark vessels by aging last_seen and deactivating AIS.
    vessels = manager.fusion.ais_tracker.get_all_vessels()
    for vessel in vessels[:2]:
        vessel.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
        vessel.ais_active = False

    # Build 5 synthetic SAR detections: 3 matched, 2 unmatched.
    now = datetime.now(timezone.utc)
    synthetic = []
    for idx, vessel in enumerate(vessels[:3]):
        lat, lon = vessel.last_position
        synthetic.append(
            SARDetection(
                detection_id=f"demo-match-{idx}",
                image_id="demo-image",
                bbox=(10.0 * idx, 20.0, 10.0 * idx + 30.0, 55.0),
                geo_position=(lat, lon),
                confidence=0.81,
                class_name="ship",
                estimated_length_meters=120.0,
                estimated_width_meters=25.0,
                heading_deg=vessel.last_heading_deg,
                speed_knots=vessel.last_speed_knots,
                model_used="stub",
                timestamp=now,
            )
        )
    synthetic.extend(
        [
            SARDetection(
                detection_id="demo-dark-1",
                image_id="demo-image",
                bbox=(100.0, 100.0, 170.0, 140.0),
                geo_position=(26.8, 49.7),
                confidence=0.88,
                class_name="ship",
                estimated_length_meters=180.0,
                estimated_width_meters=35.0,
                heading_deg=None,
                speed_knots=None,
                model_used="stub",
                timestamp=now,
            ),
            SARDetection(
                detection_id="demo-dark-2",
                image_id="demo-image",
                bbox=(200.0, 220.0, 255.0, 260.0),
                geo_position=(25.8, 56.5),
                confidence=0.77,
                class_name="ship",
                estimated_length_meters=95.0,
                estimated_width_meters=20.0,
                heading_deg=None,
                speed_knots=None,
                model_used="stub",
                timestamp=now,
            ),
        ]
    )

    picture = manager.fusion.fuse(sar_detections=synthetic)
    print(f"[2] Maritime picture stats: {picture.statistics}")

    scans = manager.scan_borders()
    alert_count = sum(len(v) for v in scans.values())
    print(f"[3] Border scan complete: zones={len(scans)} alerts={alert_count}")

    dark = manager.get_dark_vessels()
    print(f"[4] Dark vessel report count: {len(dark)}")
    for item in dark[:5]:
        print("  -", item.get("mmsi", item.get("detection_id")), item.get("last_position", item.get("geo_position")))

    events = manager.fusion.border_engine.feed_to_threat_detection(
        manager.fusion.border_engine.active_alerts[-10:]
    )
    print(f"[5] Threat events fed to Phase 5: {len(events)}")

    out = "data/sensor-analytics/demo_maritime_picture.geojson"
    manager.fusion.export_picture(out)
    print(f"[6] GeoJSON exported to {out}")


if __name__ == "__main__":
    main()
