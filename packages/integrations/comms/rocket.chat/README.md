# rocket.chat Integration

S3M communications-domain wrapper for **rocket.chat** secure and self-hosted
operational chat workflows.

## Military / Tactical Context
This adapter supports mission coordination by exposing deterministic secure-room
status snapshots for command posts in disconnected operations.

## Adapter Class
- `RocketchatAdapter`
- `integration_id = "rocket.chat"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.rocket.chat`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
