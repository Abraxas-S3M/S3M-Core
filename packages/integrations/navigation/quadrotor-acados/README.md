# quadrotor_acados Integration

S3M navigation-domain adapter for **quadrotor_acados** (`https://github.com/duynamrcv/quadrotor_acados`).

## Military / Tactical Context
This wrapper provides deterministic formation-control checks for cooperative UAV
missions where resilient navigation and spacing control are operationally critical.

## Adapter Class
- `QuadrotorAcadosAdapter`
- `integration_id = "quadrotor-acados"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.quadrotor-acados`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local acados/CasADi and build-toolchain hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
