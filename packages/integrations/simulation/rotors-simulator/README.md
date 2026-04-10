# rotors_simulator Integration

## Purpose

This adapter wraps the `rotors_simulator` repository for S3M UAV simulation workflows.

Military/tactical context: it delivers deterministic rotorcraft dynamics snapshots so autonomy controllers can be validated in repeatable, airgapped mission rehearsal loops.

## Adapter Class

- `RotorsSimulatorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.rotors-simulator`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path, ROS/Gazebo tools, and local Python module availability

## Manifest

`get_manifest()` loads integration metadata from `manifest.yaml`.
