#!/usr/bin/env python3
"""SAR detection demo for S3M Phase 15 Layer 09."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from services.sensor_analytics import SARDetector, SARImageMeta, SARPreprocessor, SARShipClassifier


def main() -> None:
    detector = SARDetector()
    classifier = SARShipClassifier()
    pre = SARPreprocessor()
    print("Backend:", detector.get_model_info())

    arr = np.zeros((512, 512), dtype=np.uint8)
    arr[120:130, 200:230] = 250
    arr[320:330, 100:125] = 240
    arr[420:440, 380:410] = 255
    image_path = Path("data/sensor-analytics/demo/sar_demo.png")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(image_path)

    detections = detector.detect(str(image_path), confidence_threshold=0.2)
    meta = SARImageMeta(
        image_id="sar-demo",
        source="local",
        filepath=str(image_path),
        width=512,
        height=512,
        acquisition_time=datetime.now(timezone.utc),
        polarization="VV",
        resolution_meters=10.0,
        center_lat=26.5,
        center_lon=50.2,
        bounds={"north": 26.7, "south": 26.3, "east": 50.4, "west": 50.0},
        metadata={},
    )

    print(f"Detections: {len(detections)}")
    for det in detections:
        cls = classifier.classify(det).value
        lat, lon = pre.pixel_to_geo((det.bbox[0] + det.bbox[2]) / 2, (det.bbox[1] + det.bbox[3]) / 2, meta)
        print(
            f"{det.detection_id[:8]} "
            f"bbox={tuple(round(v, 1) for v in det.bbox)} "
            f"geo=({lat:.4f},{lon:.4f}) "
            f"conf={det.confidence:.2f} "
            f"class={cls}"
        )


if __name__ == "__main__":
    main()
