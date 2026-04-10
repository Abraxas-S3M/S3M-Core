# WarAgent Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [WarAgent](https://github.com/agiresearch/WarAgent) in the Simulation domain.

## Military/Tactical Context
This adapter supports campaign-level red/blue rehearsal and escalation analysis in sovereign environments where planning tools must function offline.

## Adapter Class
- `WaragentAdapter` (`packages/integrations/simulation/waragent/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.waragent`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `WARAGENT_PATH` / `S3M_WARAGENT_PATH`
2. `WARAGENT_ENTRYPOINT` / `S3M_WARAGENT_ENTRYPOINT`
3. Local command availability (`waragent`)
