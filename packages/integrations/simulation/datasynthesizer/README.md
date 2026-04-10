# DataSynthesizer Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [DataSynthesizer](https://github.com/DataResponsibly/DataSynthesizer) in the Simulation domain.

## Military/Tactical Context
Enables privacy-preserving synthetic dataset generation for readiness exercises and command-post rehearsals where operational data protection is mandatory.

## Adapter Class
- `DatasynthesizerAdapter` (`packages/integrations/simulation/datasynthesizer/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.datasynthesizer`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `DATASYNTHESIZER_PATH` / `S3M_DATASYNTHESIZER_PATH`
2. `DATASYNTHESIZER_BIN` / `S3M_DATASYNTHESIZER_BIN`
3. Local Python module `DataSynthesizer` or local command binaries
