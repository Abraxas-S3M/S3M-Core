# msdllib (orbat-mapper) Integration

## Purpose

This adapter wraps related orbat-mapper/MSDL parsing components for S3M
training and simulation workflows.

Military/tactical context: it allows staff planners to convert scenario
definitions into force structures and phase timelines while preserving offline
operation for sovereign rehearsal environments.

## Adapter Class

- `MsdlliborbatMapperAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.msdllib-orbat-mapper`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture payload from
  `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path or local runtime hints

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
