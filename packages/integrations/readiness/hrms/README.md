# hrms Readiness Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [frappe/hrms](https://github.com/frappe/hrms) to support personnel and readiness workflows.

## Military/Tactical Context
Supports sovereign manning awareness by exposing deterministic personnel, attendance, and training-readiness snapshots for command planning in disconnected operations.

## Adapter Class
- `HrmsAdapter` (`packages/integrations/readiness/hrms/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.hrms`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Checks
`validate_availability()` checks:
1. `HRMS_PATH` / `S3M_HRMS_PATH`
2. Local command availability (`bench`, `frappe-bench`, `hrms`)
