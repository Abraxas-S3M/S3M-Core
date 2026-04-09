# DFIR-IRIS Integration

## Purpose

This adapter wraps DFIR-IRIS for S3M incident response case management flows.

Military/tactical context: it supports synchronized forensic command and incident tracking during cyber operations in disconnected environments.

## Adapter Class

- `DfirIrisAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.cyber.dfir-iris`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local availability checks and orchestrator handoff status response

## Manifest

`manifest.yaml` is parsed by `get_manifest()` for integration registry discovery.
