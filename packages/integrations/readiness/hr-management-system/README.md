# hr-management-system Integration

## Purpose

This adapter wraps the hr-management-system repository for S3M personnel and readiness oversight.

Military/tactical context: it provides deterministic offline outputs and local availability checks so force managers can evaluate staffing and administrative readiness without external network dependency.

## Adapter Class

- `HrManagementSystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.hr-management-system`

## Operational Modes

- **Airgapped mode**: fixture replay from `fixtures/sample_response.json`
- **Online mode**: runtime/tool presence checks with standardized status response

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
