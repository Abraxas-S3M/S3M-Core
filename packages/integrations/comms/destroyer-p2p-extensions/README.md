# Destroyer_P2P (extensions) Integration

S3M communications-domain wrapper for **Destroyer_P2P (extensions)**.

## Military / Tactical Context
This adapter helps sovereign command elements assess and orchestrate secure
communications channels while operating in contested or disconnected theaters.

## Adapter Class
- `DestroyerP2pextensionsAdapter`
- `integration_id = "destroyer-p2p-extensions"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.destroyer-p2p-extensions`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
