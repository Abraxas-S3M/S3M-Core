# lidar_radar_fusion_ekf_ukf Integration

## Purpose

This adapter wraps **lidar_radar_fusion_ekf_ukf** for S3M LiDAR/radar state-estimation workflows.

Military/tactical context: it supports robust track estimation for fire-control and air-defense chains under degraded visibility and contested electromagnetic conditions.

## Adapter Class

- `LidarRadarFusionEkfAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.lidar-radar-fusion-ekf-ukf`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local toolchain checks with no external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
