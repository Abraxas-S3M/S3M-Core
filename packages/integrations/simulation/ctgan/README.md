# CTGAN Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [CTGAN](https://github.com/sdv-dev/CTGAN) in the Simulation domain.

## Military/Tactical Context
Supports synthetic force-structure and logistics data generation so planners can rehearse mission scenarios without exposing sensitive operational records.

## Adapter Class
- `CtganAdapter` (`packages/integrations/simulation/ctgan/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.ctgan`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `CTGAN_PATH` / `S3M_CTGAN_PATH`
2. `CTGAN_BIN` / `S3M_CTGAN_BIN`
3. Local Python modules (`ctgan`, `sdv`) or command binaries
