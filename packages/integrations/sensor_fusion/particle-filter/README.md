# particle_filter Integration

## Purpose

This adapter wraps **particle_filter** for S3M sensor-fusion localization workflows.

Military/tactical context: it enables resilient pose estimation in GPS-contested zones by replaying deterministic fixture outputs during offline mission planning and validation.

## Adapter Class

- `ParticleFilterAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.particle-filter`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local ROS2/toolchain readiness checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
