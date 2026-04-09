# Limited; adapt OpenMAINT Integration

S3M military-domain wrapper for **OpenMAINT** adaptation workflows.

## Military / Tactical Context
This adapter supports military procurement and sustainment teams with local
maintenance-readiness snapshots for mission-critical infrastructure and fleets.

## Adapter Class
- `LimitedAdaptOpenmaintAdapter`
- `integration_id = "limited;-adapt-openmaint"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` verifies local binaries or local deployment paths.
- `execute()` returns deterministic fixture data when in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
