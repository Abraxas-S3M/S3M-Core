# snipe-it Integration

S3M maintenance-domain wrapper for **snipe-it** asset and maintenance lifecycle
coordination.

## Military / Tactical Context
This adapter helps sustainment teams preserve accountability for mission assets
and identify maintenance risk before readiness degradation in contested theaters.

## Adapter Class
- `SnipeItAdapter`
- `integration_id = "snipe-it"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.snipe-it`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
