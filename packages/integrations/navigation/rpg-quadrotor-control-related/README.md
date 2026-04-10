# rpg_quadrotor_control (related) Integration

S3M navigation-domain adapter for **rpg_quadrotor_control** (`https://github.com/uzh-rpg/rpg_quadrotor_control`).

## Military / Tactical Context
This adapter provides deterministic control-stack readiness checks for quadrotor ISR and rapid-response maneuver missions in airgapped operational theaters.

## Adapter Class
- `RpgQuadrotorControlrelatedAdapter`
- `integration_id = "rpg-quadrotor-control-related"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.rpg-quadrotor-control-related`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS/catkin/control runtime indicators.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
