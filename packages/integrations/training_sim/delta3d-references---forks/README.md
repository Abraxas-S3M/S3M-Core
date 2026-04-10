# Delta3D references / forks Training & Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Delta3D forks and related military simulation engine references.

## Military/Tactical Context
Supports command-post rehearsal and 3D mission environment preparation by standardizing Delta3D-derived simulation assets in disconnected deployments.

## Adapter Class
- `Delta3dReferencesForksAdapter` (`packages/integrations/training_sim/delta3d-references---forks/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.training_sim.delta3d-references---forks`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `DELTA3D_REFERENCES_FORKS_PATH` / `S3M_DELTA3D_REFERENCES_FORKS_PATH`
2. `DELTA3D_REFERENCES_FORKS_ROOT` / `S3M_DELTA3D_REFERENCES_FORKS_ROOT`
3. Local command availability (`cmake`, `python3`, `git`)
