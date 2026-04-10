# synapse (Matrix homeserver) Integration

S3M communications-domain wrapper for **synapse (Matrix homeserver)** secure
federated messaging workflows.

## Military / Tactical Context
This adapter supports encrypted command-and-control collaboration across
federated nodes while preserving mission continuity during disconnected
operations.

## Adapter Class
- `SynapsematrixHomeserverAdapter`
- `integration_id = "synapse-matrix-homeserver"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.synapse-matrix-homeserver`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
