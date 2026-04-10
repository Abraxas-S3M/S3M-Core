# detectron2 Integration

S3M sensor-fusion adapter for **detectron2** (`https://github.com/facebookresearch/detectron2`).

## Military / Tactical Context
This adapter supports deterministic validation of detection and segmentation readiness for tactical scene understanding in disconnected and contested deployments.

## Adapter Class
- `Detectron2Adapter`
- `integration_id = "detectron2"`
- `domain = "sensor_fusion"`
- Logger: `s3m.integrations.sensor_fusion.detectron2`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
