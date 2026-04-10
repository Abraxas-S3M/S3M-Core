# M3DGR Integration

## Purpose

This adapter wraps **M3DGR** for S3M sensor-fusion workflows.

Military/tactical context: it provides deterministic fused-SLAM readiness checks for LiDAR-camera-IMU pipelines in denied or contested electromagnetic environments.

## Adapter Class

- `M3dgrAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.m3dgr`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks without external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
