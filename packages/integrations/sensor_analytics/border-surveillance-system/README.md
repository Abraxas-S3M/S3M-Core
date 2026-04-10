# Border-Surveillance-System Integration

## Purpose

This adapter wraps the
[Border-Surveillance-System](https://github.com/subhayudas/Border-Surveillance-System)
project for S3M border sensor analytics workflows.

Military/tactical context: fixed and mobile surveillance assets must identify
intruders, drones, and vessel activity rapidly while preserving sovereign,
offline execution in contested network environments.

## Adapter Class

- `BorderSurveillanceSystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.border-surveillance-system`

## Operational Modes

- **Airgapped mode**: `execute()` returns deterministic fixture payloads from
  `fixtures/sample_response.json`.
- **Online mode**: validates local runtime prerequisites only; no external API
  usage occurs.

## Manifest

Metadata is declared in `manifest.yaml` and surfaced by `get_manifest()`.
