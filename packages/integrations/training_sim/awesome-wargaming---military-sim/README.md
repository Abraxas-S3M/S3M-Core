# awesome-wargaming / military-sim Training & Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for curated awesome lists and military simulation topic collections.

## Military/Tactical Context
Supports doctrine and training cells by cataloging sovereign-usable open-source wargaming simulators for rapid exercise design in disconnected environments.

## Adapter Class
- `AwesomeWargamingMilitaryAdapter` (`packages/integrations/training_sim/awesome-wargaming---military-sim/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.training_sim.awesome-wargaming---military-sim`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `AWESOME_WARGAMING_MILITARY_SIM_PATH` / `S3M_AWESOME_WARGAMING_MILITARY_SIM_PATH`
2. `AWESOME_WARGAMING_MILITARY_SIM_ROOT` / `S3M_AWESOME_WARGAMING_MILITARY_SIM_ROOT`
3. Local command availability (`python3`, `git`)
