# MSG201CWIX Integration

## Purpose

This adapter wraps the MSG201CWIX repository for S3M coalition interoperability exercise workflows.

Military/tactical context: it helps mission engineering teams validate CWIX C2SIM data exchanges with deterministic outputs before deploying to contested-network rehearsal environments.

## Adapter Class

- `Msg201cwixAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.msg201cwix`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks without external API calls

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
