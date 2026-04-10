# openremote Integration

## Purpose

This adapter wraps [openremote](https://github.com/openremote/openremote) fleet
telematics examples for S3M maintenance and readiness workflows.

Military/tactical context: operators can assess convoy vehicle health and
pre-failure indicators on sovereign nodes without exposing telemetry externally.

## Adapter Class

- `OpenremoteAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.maintenance.openremote`

## Operational Modes

- **Airgapped mode**: `execute()` returns deterministic fixture data from
  `fixtures/sample_response.json`.
- **Online mode**: validates local tooling presence only; external APIs are not called.

## Manifest

Adapter metadata is declared in `manifest.yaml` and returned by `get_manifest()`.
