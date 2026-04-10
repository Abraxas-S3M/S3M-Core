# kinematic_arbiter Integration

## Purpose

This adapter wraps the `kinematic_arbiter` repository to expose mediated EKF
sensor-fusion readiness checks inside S3M.

Military/tactical context: this wrapper supports deterministic validation of
state-estimation pipelines for maneuver units operating with intermittent sensor
feeds in contested environments.

## Adapter Class

- `KinematicArbiterAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.kinematic-arbiter`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`
- **Online mode**: validates local ROS2/CLI dependencies before runtime handoff

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via
`get_manifest()`.
