# Mergekit Integration

## Purpose

This adapter wraps Mergekit so S3M can validate sovereign model-merging readiness in controlled environments.

Military/tactical context: it supports auditable preparation of mission-specific composite models without exposing weights to external services.

## Adapter Class

- `MergekitAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.core_tooling.mergekit`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/module checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
