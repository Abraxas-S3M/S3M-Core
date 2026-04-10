# player-tool Integration

S3M sensor-analytics adapter for **player-tool**
(`https://github.com/alvarolb/player-tool`).

## Military / Tactical Context
This wrapper supports maritime ISR and coastal security missions by validating
local simulation/data-fusion readiness with deterministic airgapped output.

## Adapter Class
- `PlayerToolAdapter`
- `integration_id = "player-tool"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.player-tool`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local module/binary readiness.
- `execute()` returns fixture-backed output in airgapped mode.

## Airgapped Fixture
Fixture path: `fixtures/sample_response.json`
