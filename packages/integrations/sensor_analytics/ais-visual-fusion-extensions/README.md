# AIS-Visual-Fusion Extensions Integration

## Purpose

This adapter wraps extension workflows around AIS-Visual-Fusion for S3M
multi-view vessel analytics.

Military/tactical context: maritime command cells require fused AIS, video, and
satellite track continuity to maintain a sovereign common operating picture and
prioritize non-cooperative contacts in denied communications environments.

## Adapter Class

- `AisVisualFusionExtensionsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.ais-visual-fusion-extensions`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from
  `fixtures/sample_response.json`.
- **Online mode**: performs only local readiness checks and no external API
  usage.

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
