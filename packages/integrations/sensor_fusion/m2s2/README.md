# M2S2 Integration

## Purpose

This adapter wraps **M2S2** for S3M sensor fusion workflows.

Military/tactical context: it validates multi-modal sensor suite readiness so surveillance and perimeter defense decisions can rely on resilient cross-sensor corroboration in denied-network operations.

## Adapter Class

- `M2s2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.m2s2`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: checks local ROS2/M2S2 command availability only

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
