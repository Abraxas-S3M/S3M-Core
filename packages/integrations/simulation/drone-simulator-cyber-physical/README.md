# drone_simulator (cyber-physical) Integration

S3M adapter for [drone_simulator](https://github.com/patilunmesh/drone_simulator) in the `simulation` domain.

## Tactical purpose

This wrapper enables sovereign cyber-physical UAV exercise orchestration by
checking local ROS2/Gazebo readiness and exposing deterministic offline
responses for attack/defense rehearsal scenarios.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime availability (path, binary, module probes)
- Returns deterministic fixture output in airgapped mode

## Airgapped behavior

With airgapped mode enabled, `execute()` returns
`fixtures/sample_response.json` to emulate cyber-physical drone engagement
results without external dependencies.
