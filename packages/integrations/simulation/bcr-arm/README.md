# bcr_arm Integration

S3M adapter for [bcr_arm](https://github.com/blackcoffeerobotics/bcr_arm) in the `simulation` domain.

## Tactical purpose

This wrapper supports sovereign rehearsal of robotic arm operations for
high-risk handling missions by validating local ROS2/Gazebo/Isaac simulation
dependencies and replaying deterministic fixture outputs offline.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime availability (path, binary, module probes)
- Returns deterministic fixture output in airgapped mode

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` for
deterministic simulation output without external connectivity.
