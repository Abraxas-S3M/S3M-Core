# Destroyer_P2P Integration

S3M communications-domain wrapper for **Destroyer_P2P** quantum-resistant
peer-to-peer secure chat operations.

## Military / Tactical Context
This adapter supports hardened comms continuity by exposing deterministic
encryption and mesh-integrity snapshots for contested signal environments.

## Adapter Class
- `DestroyerP2pAdapter`
- `integration_id = "destroyer-p2p"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.destroyer-p2p`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
