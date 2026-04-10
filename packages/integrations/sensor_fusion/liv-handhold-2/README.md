# LIV_handhold_2 Integration

## Purpose

This adapter wraps **LIV_handhold_2** for S3M sensor-fusion workflows.

Military/tactical context: it supports low-cost dismounted 3D mapping and localization readiness checks for teams operating in denied communications environments.

## Adapter Class

- `LivHandhold2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.liv-handhold-2`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks without external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
