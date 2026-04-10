# sar-ship-detect Integration

S3M sensor-analytics wrapper for **sar-ship-detect** (`https://github.com/armkhudinyan/sar-ship-detect`).

## Military / Tactical Context
This adapter supports maritime surveillance units by classifying SAR contacts
into vessel categories for rapid threat triage in disconnected operations.

## Adapter Class
- `SarShipDetectAdapter`
- `integration_id = "sar-ship-detect"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.sar-ship-detect`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
