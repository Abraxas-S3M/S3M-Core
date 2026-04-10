# Ship-Detection-Using-Satellite-Imagery Integration

S3M sensor-analytics wrapper for **Ship-Detection-Using-Satellite-Imagery** (`https://github.com/Dhruvisha29/Ship-Detection-Using-Satellite-Imagery`).

## Military / Tactical Context
This adapter supports maritime domain awareness by extracting optical vessel
contacts for cross-cueing with SAR and other reconnaissance feeds.

## Adapter Class
- `ShipDetectionUsingSatelliteAdapter`
- `integration_id = "ship-detection-using-satellite-imagery"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.ship-detection-using-satellite-imagery`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
