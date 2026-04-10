# WargamesAI Integration

## Purpose

This adapter wraps the upstream **WargamesAI** repository for S3M training and simulation workflows.

Military/tactical context: it enables deterministic outputs for professional wargame planning, execution, and after-action review when operating in sovereign airgapped environments.

## Adapter Class

- `WargamesaiAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.wargamesai`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local tool availability and returns runtime readiness status

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
