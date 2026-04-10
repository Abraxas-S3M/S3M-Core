# WarGamesAI extensions Training & Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for forks/extensions of `user1342/WargamesAI` used for scenario generation.

## Military/Tactical Context
Enables staff-level mission planning cells to generate and compare red/blue course-of-action variants during disconnected wargame rehearsal cycles.

## Adapter Class
- `WargamesaiExtensionsAdapter` (`packages/integrations/training_sim/wargamesai-extensions/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.training_sim.wargamesai-extensions`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `WARGAMESAI_EXTENSIONS_PATH` / `S3M_WARGAMESAI_EXTENSIONS_PATH`
2. `WARGAMESAI_EXTENSIONS_ROOT` / `S3M_WARGAMESAI_EXTENSIONS_ROOT`
3. Local command availability (`python3`, `git`)
