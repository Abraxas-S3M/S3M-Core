# Awesome-Geospatial Integration

S3M sensor-analytics adapter for **Awesome-Geospatial**
(`https://github.com/sacridini/Awesome-Geospatial`).

## Military / Tactical Context
This wrapper supports ISR toolchain selection by surfacing curated geospatial
resources under disconnected operating conditions with deterministic outputs.

## Adapter Class
- `AwesomeGeospatialAdapter`
- `integration_id = "awesome-geospatial"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.awesome-geospatial`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local mirror/path readiness.
- `execute()` returns fixture-backed output in airgapped mode.

## Airgapped Fixture
Fixture path: `fixtures/sample_response.json`
