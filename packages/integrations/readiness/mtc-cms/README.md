# mtc-cms Integration

## Purpose

This adapter wraps the mtc-cms repository for S3M training certification and readiness tracking.

Military/tactical context: it helps training command staff assess qualification continuity and mission deployability risk while operating in sovereign, disconnected infrastructure.

## Adapter Class

- `MtcCmsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.mtc-cms`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime/tooling probe with readiness-friendly status response

## Manifest

The adapter loads metadata from `manifest.yaml` via `get_manifest()`.
