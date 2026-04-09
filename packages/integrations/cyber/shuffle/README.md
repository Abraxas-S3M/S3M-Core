# shuffle Integration

## Purpose

This adapter wraps the Shuffle SOAR repository for S3M cyber automation workflows.

Military/tactical context: it enables deterministic security playbook rehearsal so defensive actions can be validated before use in contested operations.

## Adapter Class

- `ShuffleAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.cyber.shuffle`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: checks local command/path readiness and reports orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
