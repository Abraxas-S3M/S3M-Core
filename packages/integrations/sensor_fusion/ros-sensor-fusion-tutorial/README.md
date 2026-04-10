# ros-sensor-fusion-tutorial Integration

## Purpose

This adapter wraps **ros-sensor-fusion-tutorial** for S3M sensor-fusion state-estimation workflows.

Military/tactical context: it enables deterministic EKF/UKF fusion rehearsals for mission planning where comms are restricted and reproducibility is required.

## Adapter Class

- `RosSensorFusionTutorialAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.ros-sensor-fusion-tutorial`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local ROS/runtime checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
