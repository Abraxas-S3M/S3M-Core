# custom-scripts Integration

## Purpose

This adapter wraps the
[custom-scripts](https://github.com/sentinel-hub/custom-scripts) repository for
S3M Sentinel-1/2 processing workflows.

Military/tactical context: ISR teams use this wrapper to standardize scripted
satellite scene analytics for coastal and border monitoring while command nodes
operate in disconnected or denied-network environments.

## Adapter Class

- `CustomScriptsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.custom-scripts`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from
  `fixtures/sample_response.json`.
- **Online mode**: checks local runtime/tooling availability only and performs
  no external API calls.

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
