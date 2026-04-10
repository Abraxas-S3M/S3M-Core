# awesome-synthetic-data Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [awesome-synthetic-data](https://github.com/statice/awesome-synthetic-data) in the Simulation domain.

## Military/Tactical Context
Gives simulation planners a curated offline reference to identify synthetic-data tooling for mission rehearsal pipelines and red/blue force analytic drills.

## Adapter Class
- `AwesomeSyntheticDataAdapter` (`packages/integrations/simulation/awesome-synthetic-data/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.awesome-synthetic-data`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `AWESOME_SYNTHETIC_DATA_PATH` / `S3M_AWESOME_SYNTHETIC_DATA_PATH`
2. `vendor_path` from `manifest.yaml` if configured
3. Local command availability (`git`) for catalog management
