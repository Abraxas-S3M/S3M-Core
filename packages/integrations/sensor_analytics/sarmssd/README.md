# SARMSSD Integration

S3M sensor-analytics wrapper for **SARMSSD**.

## Military / Tactical Context
This adapter supports maritime target detection workflows using SAR imagery and
YOLO-based models so analysts can triage surface contacts without external
network dependencies.

## Adapter Class
- `SarmssdAdapter`
- `integration_id = "sarmssd"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime and configured binary/path hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
