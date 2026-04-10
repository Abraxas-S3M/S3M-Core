# arabic-summarization-with-araBert Integration

## Purpose

This adapter wraps the `arabic-summarization-with-araBert` repository for secure communications workflows in S3M.

Military/tactical context: it supports resilient mission communications by enforcing local validation and deterministic fixture-based behavior when disconnected from external networks.

## Adapter Class

- `ArabicSummarizationWithArabertAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.comms.arabic-summarization-with-arabert`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local toolchain availability and returns orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
