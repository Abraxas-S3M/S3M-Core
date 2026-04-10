# sensor_fusion Integration

## Purpose

This adapter wraps **sensor_fusion** implementations (LKF, EKF, UKF, Particle Filter) for S3M state-estimation pipelines.

Military/tactical context: it helps evaluate estimator quality for target tracking and maneuver prediction under noisy contested-environment sensor feeds.

## Adapter Class

- `SensorFusionAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.sensor-fusion`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks with no external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
