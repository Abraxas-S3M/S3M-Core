# WSC2 Integration

S3M comms-domain wrapper for **WSC2** secure WebSocket command-routing
operations.

## Military / Tactical Context
This adapter supports sovereign command-and-control continuity by exposing
route-health telemetry for encrypted WebSocket channels in contested networks.

## Adapter Class
- `Wsc2Adapter`
- `integration_id = "wsc2"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.wsc2`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
