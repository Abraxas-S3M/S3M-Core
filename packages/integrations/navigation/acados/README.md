# acados Integration

S3M navigation-domain adapter for **acados** (`https://github.com/acados/acados`).

## Military / Tactical Context
This adapter enables deterministic nonlinear MPC rehearsal for mission-critical
vehicle control in disconnected and bandwidth-denied environments.

## Adapter Class
- `AcadosAdapter`
- `integration_id = "acados"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.acados`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local acados paths/modules/toolchain binaries.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
