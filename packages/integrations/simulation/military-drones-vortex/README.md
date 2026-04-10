# Military_Drones (VorteX) Integration

S3M adapter for [VorteX](https://github.com/Manohara-Ai/VorteX) in the `simulation` domain.

## Tactical purpose

This wrapper supports sovereign multi-drone surveillance rehearsal by
validating local ROS2/Gazebo Harmonic runtime prerequisites and returning
deterministic fixture payloads in disconnected command conditions.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime availability (path, binary, module probes)
- Returns deterministic fixture output in airgapped mode

## Airgapped behavior

When airgapped mode is active, `execute()` returns
`fixtures/sample_response.json` to emulate multi-drone mission outputs without
network dependency.
