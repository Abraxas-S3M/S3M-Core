# warshard Integration

## Purpose

This adapter wraps the upstream **warshard** repository for S3M training and simulation workflows.

Military/tactical context: it supplies deterministic combined-arms rehearsal outputs for planning and experimentation in offline sovereign environments.

## Adapter Class

- `WarshardAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.warshard`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local runtime availability and returns readiness state

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
