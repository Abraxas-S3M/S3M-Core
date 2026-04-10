# YOLOV8_SAR_SHIP_DETECTION Integration

S3M sensor-analytics wrapper for **YOLOV8_SAR_SHIP_DETECTION** (`https://github.com/sethubolt7/YOLOV8_SAR_SHIP_DETECTION`).

## Military / Tactical Context
This adapter supports maritime interdiction planning by providing oriented ship
detections from SAR scenes, improving heading-aware contact interpretation.

## Adapter Class
- `Yolov8SarShipDetectionAdapter`
- `integration_id = "yolov8-sar-ship-detection"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.yolov8-sar-ship-detection`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
