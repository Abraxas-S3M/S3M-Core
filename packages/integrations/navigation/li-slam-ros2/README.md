# li_slam_ros2 Integration

## Purpose

This adapter wraps li_slam_ros2 to expose tightly-coupled LiDAR/IMU SLAM readiness for S3M edge navigation services.

Military/tactical context: this wrapper helps operators confirm that
mission navigation pipelines remain deterministic and auditable on isolated
edge nodes before live deployment.

## Adapter Class

- `LiSlamRos2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.li-slam-ros2`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/path availability for the wrapped stack

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via `get_manifest()`.
