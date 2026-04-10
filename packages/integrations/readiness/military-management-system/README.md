# Military-Management-System Integration

## Purpose

This adapter wraps the Military-Management-System repository for S3M readiness and personnel administration workflows.

Military/tactical context: it standardizes local access checks and offline fixture outputs so command elements can rehearse readiness rollups without external dependencies.

## Adapter Class

- `MilitaryManagementSystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.military-management-system`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture response from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path or local runtime commands

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
