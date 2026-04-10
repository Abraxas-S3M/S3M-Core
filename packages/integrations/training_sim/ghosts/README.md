# ghosts Integration

## Purpose

This adapter wraps the ghosts cyber-range repository for S3M training and simulation workflows.

Military/tactical context: it enables realistic joint cyber exercise rehearsal and defensive mission training while remaining operational in sovereign disconnected infrastructure.

## Adapter Class

- `GhostsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.ghosts`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture response from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path or common local runtime commands

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
