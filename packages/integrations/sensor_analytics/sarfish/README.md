# SARFish Integration

S3M sensor-analytics wrapper for **SARFish**.

## Military / Tactical Context
This adapter helps maritime surveillance teams process SAR scenes for ship
detection in denied or bandwidth-constrained theaters where local-only workflows
are mandatory.

## Adapter Class
- `SarfishAdapter`
- `integration_id = "sarfish"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime and configured binary/path hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
