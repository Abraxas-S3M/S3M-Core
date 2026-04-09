# mpc_planner Integration

S3M navigation-domain adapter for **mpc_planner** (`https://github.com/tud-amr/mpc_planner`).

## Military / Tactical Context
This wrapper supports deterministic dynamic-obstacle planning checks for UGV and
convoy routing in contested environments with intermittent communications.

## Adapter Class
- `MpcPlannerAdapter`
- `integration_id = "mpc-planner"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.mpc-planner`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS/solver command and module hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
