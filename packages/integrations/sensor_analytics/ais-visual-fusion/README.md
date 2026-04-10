# AIS-Visual-Fusion Integration

## Purpose

This adapter wraps the
[AIS-Visual-Fusion](https://github.com/QuJX/AIS-Visual-Fusion) repository for
S3M maritime sensing workflows.

Military/tactical context: coastal surveillance requires fusion of non-imaging
telemetry (AIS) and EO/IR feeds to identify non-cooperative vessels and keep an
accurate sovereign maritime common operating picture.

## Adapter Class

- `AisVisualFusionAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.ais-visual-fusion`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from
  `fixtures/sample_response.json`.
- **Online mode**: checks only local runtime/tooling availability and does not
  perform external API access.

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
