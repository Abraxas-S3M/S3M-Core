# GeoTrackNet Integration

S3M sensor-analytics wrapper for **GeoTrackNet**.

## Military / Tactical Context
This adapter supports maritime surveillance operations by surfacing probable AIS
track anomalies that may indicate smuggling, spoofing, or hostile route
deviation. It remains functional in airgapped deployments through deterministic
fixture responses.

## Adapter Class
- `GeotracknetAdapter`
- `integration_id = "geotracknet"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime and configured binary/path hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
