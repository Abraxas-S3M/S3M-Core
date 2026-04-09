# military-management-FE Integration

## Purpose

This adapter wraps the `military-management-FE` repository for S3M military
asset and logistics workflows.

Military/tactical context: it enables offline readiness snapshots so commanders
can assess movement and sustainment posture before issuing maneuver directives.

## Adapter Class

- `MilitaryManagementFeAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.military-management-fe`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: checks local command/path readiness and reports adapter
  status for orchestrator pipelines

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
