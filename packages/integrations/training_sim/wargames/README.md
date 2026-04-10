# Wargames Integration

## Purpose

This adapter wraps the upstream **Wargames** repository for S3M training and simulation workflows.

Military/tactical context: it provides deterministic terrain and unit-mechanics simulation outputs for mission rehearsal in disconnected sovereign operations centers.

## Adapter Class

- `WargamesAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.wargames`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local Java/runtime dependencies and returns readiness state

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
