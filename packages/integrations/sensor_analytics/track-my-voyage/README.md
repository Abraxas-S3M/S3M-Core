# TRACK-MY-VOYAGE Integration

S3M sensor-analytics wrapper for **TRACK-MY-VOYAGE**.

## Military / Tactical Context
This adapter supports remote-sensing intelligence workflows where maritime or
border observations must remain reliable in sovereign, airgapped deployments.

## Adapter Class
- `TrackMyVoyageAdapter`
- `integration_id = "track-my-voyage"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths.
- `execute()` returns deterministic fixture payloads in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
