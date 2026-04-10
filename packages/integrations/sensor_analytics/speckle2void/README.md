# speckle2void Integration

S3M sensor-analytics wrapper for **speckle2void**.

## Military / Tactical Context
This adapter supports SAR image-denoising workflows that improve maritime target
interpretation quality for ISR analysts operating in offline and contested
network environments.

## Adapter Class
- `Speckle2voidAdapter`
- `integration_id = "speckle2void"`
- `domain = "sensor_analytics"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime and configured binary/path hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
