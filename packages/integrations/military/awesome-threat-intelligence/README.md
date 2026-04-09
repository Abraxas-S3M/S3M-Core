# awesome-threat-intelligence Integration

## Purpose

This adapter wraps the `awesome-threat-intelligence` repository for S3M military
threat intelligence workflows.

Military/tactical context: it supports offline curation of missile and UAV
threat references so analysts can maintain detection playbook readiness in
contested environments.

## Adapter Class

- `AwesomeThreatIntelligenceAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.awesome-threat-intelligence`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: checks local command/path readiness and reports adapter
  status for intelligence orchestration

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
