# ODIN (C2IS) Integration

S3M swarm-domain adapter for **ODIN** (`https://github.com/syncpoint/ODIN`).

## Military / Tactical Context
This adapter provides deterministic C2IS wrapper behavior for command elements
that must sustain track and order synchronization in disconnected operations.

## Adapter Class
- `Odinc2isAdapter`
- `integration_id = "odin-c2is"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.odin-c2is`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local C2IS runtime hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
