# geoai Integration

S3M sensor-analytics wrapper for **geoai**.

## Military / Tactical Context
This adapter supports remote-sensing intelligence workflows that fuse and
segment satellite data for area monitoring, activity change detection, and
coastal security analysis in offline deployments.

## Adapter Class
- `GeoaiAdapter`
- `integration_id = "geoai"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime and configured binary/path hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
