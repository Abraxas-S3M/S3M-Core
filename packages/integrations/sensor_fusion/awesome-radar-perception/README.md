# awesome-radar-perception Integration

## Purpose

This adapter wraps **awesome-radar-perception** for S3M sensor-fusion workflows.

Military/tactical context: it provides offline-access validation and deterministic reference snapshots to support radar detection/tracking/fusion planning under disconnected operations.

## Adapter Class

- `AwesomeRadarPerceptionAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.awesome-radar-perception`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks without external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
