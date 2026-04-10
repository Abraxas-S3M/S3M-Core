# segment-geospatial Integration

S3M sensor-analytics adapter for **segment-geospatial** (`https://github.com/opengeos/segment-geospatial`).

## Military / Tactical Context
This wrapper supports ISR mission analysis by validating local geospatial segmentation
readiness and providing deterministic fallback outputs in disconnected theaters.

## Adapter Class
- `SegmentGeospatialAdapter`
- `integration_id = "segment-geospatial"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.segment-geospatial`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks for locally available binaries/modules.
- `execute()` returns fixture-backed results in airgapped mode.

## Airgapped Fixture
Fixture path: `fixtures/sample_response.json`
