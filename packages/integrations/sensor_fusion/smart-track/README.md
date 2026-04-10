# smart_track Integration

## Purpose

This adapter wraps the `smart_track` repository for multi-modal RGB-Depth-LiDAR
tracking integration in S3M sensor-fusion workflows.

Military/tactical context: this wrapper enables deterministic replay of
multi-sensor object tracking outcomes for mission rehearsal under contested
communications conditions.

## Adapter Class

- `SmartTrackAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.smart-track`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`
- **Online mode**: validates local ROS2/CLI dependencies before runtime handoff

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via
`get_manifest()`.
