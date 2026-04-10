# Ship-Detection-on-Remote-Sensing-Synthetic-Aperture-Radar-Data Integration

S3M sensor-analytics wrapper for **Ship-Detection-on-Remote-Sensing-Synthetic-Aperture-Radar-Data** (`https://github.com/jasonmanesis/Ship-Detection-on-Remote-Sensing-Synthetic-Aperture-Radar-Data`).

## Military / Tactical Context
This adapter supports maritime ISR teams by combining multiple detector outputs
to improve contact confidence before tactical cueing decisions.

## Adapter Class
- `ShipDetectionOnRemoteAdapter`
- `integration_id = "ship-detection-on-remote-sensing-synthet"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.ship-detection-on-remote-sensing-synthet`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
