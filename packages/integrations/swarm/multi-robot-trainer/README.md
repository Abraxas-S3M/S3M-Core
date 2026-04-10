# multi_robot_trainer Integration

S3M swarm-domain adapter for **multi_robot_trainer** (`https://github.com/zmk5/multi_robot_trainer`).

## Military / Tactical Context
This adapter provides deterministic wrapper behavior for multi-robot RL training
used to prepare cooperative reconnaissance and maneuver policies in airgapped
deployment zones.

## Adapter Class
- `MultiRobotTrainerAdapter`
- `integration_id = "multi-robot-trainer"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.multi-robot-trainer`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2 and RL runtime hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
