# rpg_mpc Integration

S3M navigation-domain adapter for **rpg_mpc** (`https://github.com/uzh-rpg/rpg_mpc`).

## Military / Tactical Context
This adapter supports deterministic quadrotor MPC validation for ISR, perimeter
tracking, and convoy overwatch missions in airgapped deployments.

## Adapter Class
- `RpgMpcAdapter`
- `integration_id = "rpg-mpc"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.rpg-mpc`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS/toolchain hints and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
