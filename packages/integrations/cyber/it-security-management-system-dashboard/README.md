# IT-Security-Management-System-Dashboard Integration

## Purpose

This adapter wraps `IT-Security-Management-System-Dashboard` for S3M cyber defense workflows.

Military/tactical context: the adapter allows SOC command teams to rehearse incident triage dashboards in disconnected operational theaters.

## Adapter Class

- `ItSecurityManagementSystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.cyber.it-security-management-system-dashboard`

## Operational Modes

- **Airgapped mode**: serves `fixtures/sample_response.json`
- **Online mode**: validates local binary/path configuration and returns readiness metadata

## Manifest

`manifest.yaml` holds adapter metadata and is parsed by `get_manifest()`.
