# SAR-Ship-Dataset Integration

S3M sensor-analytics wrapper for **SAR-Ship-Dataset** (`https://github.com/CAESAR-Radi/SAR-Ship-Dataset`).

## Military / Tactical Context
This adapter supports model-governance and retraining pipelines by exposing
deterministic SAR dataset statistics for maritime readiness validation.

## Adapter Class
- `SarShipDatasetAdapter`
- `integration_id = "sar-ship-dataset"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.sar-ship-dataset`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
