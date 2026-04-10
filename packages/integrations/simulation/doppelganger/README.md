# DoppelGANger Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [DoppelGANger](https://github.com/fjxmlzn/DoppelGANger) in the Simulation domain.

## Military/Tactical Context
Enables generation of synthetic mission telemetry timelines for rehearsal and training while preserving classified temporal sensor histories.

## Adapter Class
- `DoppelgangerAdapter` (`packages/integrations/simulation/doppelganger/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.doppelganger`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `DOPPELGANGER_PATH` / `S3M_DOPPELGANGER_PATH`
2. `DOPPELGANGER_BIN` / `S3M_DOPPELGANGER_BIN`
3. Local Python modules (for example `doppelganger`, `tensorflow`) or local command binaries
