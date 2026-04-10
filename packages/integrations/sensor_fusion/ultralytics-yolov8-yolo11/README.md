# ultralytics (YOLOv8/YOLO11) Integration

S3M sensor-fusion adapter for **ultralytics** (`https://github.com/ultralytics/ultralytics`).

## Military / Tactical Context
This adapter supports deterministic edge object-detection readiness checks so tactical units can maintain rapid threat screening when disconnected from centralized compute.

## Adapter Class
- `Ultralyticsyolov8yolo11Adapter`
- `integration_id = "ultralytics-yolov8-yolo11"`
- `domain = "sensor_fusion"`
- Logger: `s3m.integrations.sensor_fusion.ultralytics-yolov8-yolo11`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local YOLO runtime hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
