# OpenC2SIM.github.io Integration

## Purpose

This adapter wraps the OpenC2SIM.github.io repository for S3M interoperability and simulation-standards workflows.

Military/tactical context: it provides deterministic access to command-and-control simulation doctrine and schema references so coalition rehearsal pipelines remain auditable in disconnected operations.

## Adapter Class

- `Openc2simgithubioAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.openc2sim.github.io`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with mission-safe readiness output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
