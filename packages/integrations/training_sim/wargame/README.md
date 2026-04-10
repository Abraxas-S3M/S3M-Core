# Wargame Integration

## Purpose

This adapter wraps the upstream **Wargame** repository for S3M training and simulation workflows.

Military/tactical context: it provides deterministic unit-level battle simulation outputs for rehearsals in disconnected, sovereign command environments.

## Adapter Class

- `WargameAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.wargame`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local Java/runtime dependencies and returns readiness state

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
