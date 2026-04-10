# multi_robot_ros2 Integration

S3M swarm-domain adapter for **multi_robot_ros2** (`https://github.com/anhbantre/multi_robot_ros2`).

## Military / Tactical Context
This wrapper validates namespace-safe multi-robot ROS2 orchestration for
distributed command-and-control mission rehearsal across mixed robot units.

## Adapter Class
- `MultiRobotRos2Adapter`
- `integration_id = "multi-robot-ros2"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.multi-robot-ros2`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2 runtime and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
