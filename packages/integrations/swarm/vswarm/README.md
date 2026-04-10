# vswarm Integration

S3M swarm-domain adapter for **vswarm** (`https://github.com/lis-epfl/vswarm`).

## Military / Tactical Context
This wrapper enables deterministic validation of communication-denied swarm
control patterns for perimeter ISR and low-signature reconnaissance missions.

## Adapter Class
- `VswarmAdapter`
- `integration_id = "vswarm"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.vswarm`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries, modules, and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
