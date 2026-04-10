# (NPS thesis prototypes) Training & Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for NPS/MOVES Institute web simulation prototypes used in officer training contexts.

## Military/Tactical Context
Supports tactical rehearsal for submarine bridge crews by exposing deterministic periscope and watchstanding simulation outputs to command training pipelines.

## Adapter Class
- `npsThesisPrototypesAdapter` (`packages/integrations/training_sim/nps-thesis-prototypes/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.training_sim.nps-thesis-prototypes`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `NPS_THESIS_PROTOTYPES_PATH` / `S3M_NPS_THESIS_PROTOTYPES_PATH`
2. `NPS_THESIS_PROTOTYPES_ROOT` / `S3M_NPS_THESIS_PROTOTYPES_ROOT`
3. Local command availability (`python3`, `node`, `npm`, `git`)
