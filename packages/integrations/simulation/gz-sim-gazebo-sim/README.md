# gz-sim (Gazebo Sim) Integration

S3M adapter for [gz-sim](https://github.com/gazebosim/gz-sim) in the `simulation` domain.

## Tactical purpose

This wrapper supports sovereign mission rehearsal by validating local Gazebo Sim
availability and exposing deterministic airgapped responses for battlefield
physics and sensor emulation workflows.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime availability (binary/path/module checks)
- Returns deterministic fixture output in airgapped mode

## Airgapped behavior

When airgapped mode is enabled, `execute()` returns
`fixtures/sample_response.json` to emulate high-fidelity mission-world outputs
without external connectivity.
