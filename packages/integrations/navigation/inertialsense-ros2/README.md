# inertialsense_ros2 Integration

## Purpose

This adapter wraps **inertialsense_ros2** for S3M navigation workflows requiring IMU/GNSS fusion status checks.

Military/tactical context: it supports degraded and denied-navigation rehearsals where RTK corrections are intermittent and inertial continuity is mission-critical.

## Adapter Class

- `InertialsenseRos2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.inertialsense-ros2`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local ROS2/runtime checks without external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
