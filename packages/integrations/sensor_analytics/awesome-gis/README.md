# awesome-gis Integration

S3M sensor-analytics adapter for **awesome-gis**
(`https://github.com/sshuair/awesome-gis`).

## Military / Tactical Context
This wrapper supports mapping and remote-sensing mission planning by exposing
curated GIS resources with deterministic responses in airgapped deployments.

## Adapter Class
- `AwesomeGisAdapter`
- `integration_id = "awesome-gis"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.awesome-gis`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local mirror/path readiness.
- `execute()` returns fixture-backed output in airgapped mode.

## Airgapped Fixture
Fixture path: `fixtures/sample_response.json`
