# erpnext Readiness Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [ERPNext](https://github.com/frappe/erpnext) in the Personnel & Readiness domain.

## Military/Tactical Context
Enables headquarters planners to monitor manning posture and personnel constraints using local ERP datasets while operating in disconnected environments.

## Adapter Class
- `ErpnextAdapter` (`packages/integrations/readiness/erpnext/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.erpnext`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `ERPNEXT_PATH` / `S3M_ERPNEXT_PATH`
2. Local command availability (`bench`, `erpnext`)
