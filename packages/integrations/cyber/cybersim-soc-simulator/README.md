# cybersim-soc-simulator Integration

## Purpose

This adapter wraps the `cybersim-soc-simulator` repository for S3M Cyber Defense Operations workflows.

Military/tactical context: the wrapper supports SOC crew rehearsal during contested operations by enabling deterministic drill playback in sovereign, airgapped deployments.

## Adapter Class

- `CybersimSocSimulatorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.cyber.cybersim-soc-simulator`

## Operational Modes

- **Airgapped mode**: returns `fixtures/sample_response.json`
- **Online mode**: validates local availability (binary/path), then returns readiness metadata for orchestrator handoff

## Manifest

Metadata is defined in `manifest.yaml` and loaded by `get_manifest()`.
