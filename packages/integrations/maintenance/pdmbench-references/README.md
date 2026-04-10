# PDMBench (references) Integration

## Purpose

This adapter wraps PDMBench-related reference repositories for S3M maintenance
benchmarking workflows.

Military/tactical context: maintenance analysts can compare predictive models
for fleet degradation patterns and select safer readiness baselines while
operating without internet access.

## Adapter Class

- `PdmbenchreferencesAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.maintenance.pdmbench-references`

## Operational Modes

- **Airgapped mode**: `execute()` returns deterministic fixture data from
  `fixtures/sample_response.json`.
- **Online mode**: only checks local runtime/path availability; no external APIs.

## Manifest

Adapter metadata is defined in `manifest.yaml` and loaded by `get_manifest()`.
