# RT-DETR Integration

S3M sensor-fusion adapter for **RT-DETR** (`https://github.com/lyuwenyu/RT-DETR`).

## Military / Tactical Context
This adapter validates transformer-based detection readiness for precision threat identification where units must sustain fast and reliable analytics under constrained communications.

## Adapter Class
- `RtDetrAdapter`
- `integration_id = "rt-detr"`
- `domain = "sensor_fusion"`
- Logger: `s3m.integrations.sensor_fusion.rt-detr`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
