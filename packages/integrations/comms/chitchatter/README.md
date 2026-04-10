# chitchatter Integration

S3M communications-domain wrapper for **chitchatter** serverless and encrypted
peer-to-peer chat workflows.

## Military / Tactical Context
This adapter supports decentralized field communications by exposing
deterministic P2P mesh telemetry for route resilience checks.

## Adapter Class
- `ChitchatterAdapter`
- `integration_id = "chitchatter"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.chitchatter`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
