# EmployeeTrackingSystem Integration

## Purpose

This adapter wraps the EmployeeTrackingSystem repository for S3M personnel attendance and status readiness workflows.

Military/tactical context: it enables sovereign accountability checks for clock-in, leave, and duty status before and during mission cycles.

## Adapter Class

- `EmployeetrackingsystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.employeetrackingsystem`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local Node.js runtime dependency presence and reports orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
