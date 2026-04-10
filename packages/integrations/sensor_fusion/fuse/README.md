# fuse Integration

S3M sensor-fusion adapter for **fuse** (`https://github.com/locusrobotics/fuse`).

## Military / Tactical Context
This wrapper standardizes nonlinear multi-sensor state-estimation readiness so mission systems can preserve navigation confidence during GPS degradation and contested electromagnetic conditions.

## Adapter Class
- `FuseAdapter`
- `integration_id = "fuse"`
- `domain = "sensor_fusion"`
- Logger: `s3m.integrations.sensor_fusion.fuse`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS/fuse runtime hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
