# enchat Integration

S3M communications-domain wrapper for **enchat** encrypted and ephemeral
terminal chat operations.

## Military / Tactical Context
This adapter supports covert communications by exposing deterministic blind
relay and ephemeral session snapshots for command-level verification.

## Adapter Class
- `EnchatAdapter`
- `integration_id = "enchat"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.enchat`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
