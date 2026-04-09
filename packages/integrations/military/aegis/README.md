# Aegis Integration

## Purpose

This adapter wraps the upstream `Aegis` repository for S3M mission orchestration.

Military/tactical context: Supports rehearsal of layered interceptor tasking so air-defense cells can evaluate response logic under compressed timelines.

## Adapter Class

- `AegisAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.aegis`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path readiness checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
