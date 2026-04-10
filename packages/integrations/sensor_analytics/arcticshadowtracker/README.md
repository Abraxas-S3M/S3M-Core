# ArcticShadowTracker Integration

## Purpose

This adapter wraps
[ArcticShadowTracker](https://github.com/henrfo/ArcticShadowTracker) for S3M
maritime surveillance workflows.

Military/tactical context: detecting dark vessels is critical for sanctions
enforcement, coastal defense, and contested-water security where hostile actors
disable AIS transponders.

## Adapter Class

- `ArcticshadowtrackerAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.arcticshadowtracker`

## Operational Modes

- **Airgapped mode**: returns fixture output from `fixtures/sample_response.json`.
- **Online mode**: performs only local dependency checks and never initiates
  external API calls.

## Manifest

Integration metadata lives in `manifest.yaml` and is exposed via `get_manifest()`.
