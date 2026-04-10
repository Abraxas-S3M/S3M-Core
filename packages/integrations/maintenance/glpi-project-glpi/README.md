# glpi-project/glpi Integration

S3M maintenance-domain wrapper for **glpi-project/glpi** service desk and
asset maintenance scheduling workflows.

## Military / Tactical Context
This adapter supports mission sustainment by surfacing maintenance schedules and
service bottlenecks that can degrade equipment readiness in operational theaters.

## Adapter Class
- `GlpiProjectglpiAdapter`
- `integration_id = "glpi-project-glpi"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.glpi-project-glpi`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
