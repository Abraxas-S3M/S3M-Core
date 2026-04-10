# Army-Tool Integration

## Purpose

This adapter wraps the Army-Tool repository for S3M personnel management and readiness monitoring.

Military/tactical context: it provides local validation and deterministic fallback outputs so headquarters staff can rehearse duty allocation and manpower readiness assessments during disconnected operations.

## Adapter Class

- `ArmyToolAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.army-tool`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local binary/path availability and reports readiness status

## Manifest

Adapter metadata is stored in `manifest.yaml` and returned by `get_manifest()`.
