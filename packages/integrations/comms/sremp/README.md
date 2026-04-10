# SREMP Integration

S3M communications-domain wrapper for **SREMP**.

## Military / Tactical Context
This adapter tracks secure relay messaging readiness for command traffic,
helping operators verify encrypted communications continuity in contested and
airgapped deployments.

## Adapter Class
- `SrempAdapter`
- `integration_id = "sremp"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.sremp`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local secure messaging dependencies.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
