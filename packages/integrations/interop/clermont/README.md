# clermont Integration

## Purpose

This adapter wraps the clermont command-center dashboard repository for S3M interoperability workflows.

Military/tactical context: it supports multi-view command-post rehearsals for operators who must coordinate tactical decisions under degraded or disconnected network conditions.

## Adapter Class

- `ClermontAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.clermont`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime validation before orchestration handoff

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
