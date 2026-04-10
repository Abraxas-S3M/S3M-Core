# FusionTracking Integration

## Purpose

This adapter wraps the `FusionTracking` repository for multi-modal EKF object
tracking integration in S3M sensor-fusion pipelines.

Military/tactical context: this wrapper supports deterministic replay of
cross-modal track association behavior for mission rehearsal on sovereign,
airgapped edge compute nodes.

## Adapter Class

- `FusiontrackingAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_fusion.fusiontracking`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from
  `fixtures/sample_response.json`
- **Online mode**: validates local runtime dependencies before accepting
  tactical track-fusion requests

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via
`get_manifest()`.
