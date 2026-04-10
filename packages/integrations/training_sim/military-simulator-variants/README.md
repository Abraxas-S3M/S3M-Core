# Military-Simulator variants Training & Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for forks/variants of `jfeng530/Military-Simulator`.

## Military/Tactical Context
Supports turn-based tactical rehearsal, force-posture experimentation, and after-action review data generation for command training elements.

## Adapter Class
- `MilitarySimulatorVariantsAdapter` (`packages/integrations/training_sim/military-simulator-variants/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.training_sim.military-simulator-variants`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `MILITARY_SIMULATOR_VARIANTS_PATH` / `S3M_MILITARY_SIMULATOR_VARIANTS_PATH`
2. `MILITARY_SIMULATOR_VARIANTS_ROOT` / `S3M_MILITARY_SIMULATOR_VARIANTS_ROOT`
3. Local command availability (`python3`, `git`)
