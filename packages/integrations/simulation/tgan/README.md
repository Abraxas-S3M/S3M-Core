# TGAN Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [TGAN](https://github.com/sdv-dev/TGAN) in the Simulation domain.

## Military/Tactical Context
Supports high-dimensional synthetic dataset generation for mission planning drills and readiness analytics without leaking sensitive force data.

## Adapter Class
- `TganAdapter` (`packages/integrations/simulation/tgan/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.tgan`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `TGAN_PATH` / `S3M_TGAN_PATH`
2. `TGAN_BIN` / `S3M_TGAN_BIN`
3. Local Python modules (`tgan`, `tensorflow`) or local command binaries
