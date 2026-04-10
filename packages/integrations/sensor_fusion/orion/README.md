# orion Integration

## Purpose

This adapter wraps the `orion` repository to provide automated target
recognition (ATR) integration points for S3M sensor-fusion workflows.

Military/tactical context: this wrapper supports deterministic validation of
vehicle recognition outputs for mission rehearsal on disconnected edge nodes.

## Adapter Class

- `OrionAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.orion`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`
- **Online mode**: validates local runtime dependencies before accepting
  handoff from tactical video-processing pipelines

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via
`get_manifest()`.
