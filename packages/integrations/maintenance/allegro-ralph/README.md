# allegro/ralph Integration

S3M maintenance-domain wrapper for **allegro/ralph** asset lifecycle and
configuration governance.

## Military / Tactical Context
This adapter supports sustainment and cyber-maintenance cells by identifying
configuration drift and maintenance liabilities that threaten mission readiness.

## Adapter Class
- `AllegroralphAdapter`
- `integration_id = "allegro-ralph"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.allegro-ralph`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
