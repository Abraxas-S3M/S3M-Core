# HRMS (Laravel) Readiness Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [amralsaleeh/HRMS](https://github.com/amralsaleeh/HRMS) with bilingual personnel administration support.

## Military/Tactical Context
Supports Arabic/English readiness workflows in multilingual commands where RTL-capable interfaces are required for accurate personnel and leave reporting.

## Adapter Class
- `HrmsLaravelAdapter` (`packages/integrations/readiness/hrms_laravel/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.hrms_laravel`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `HRMS_LARAVEL_PATH` / `S3M_HRMS_LARAVEL_PATH`
2. Local command availability (`php`, `composer`, `artisan`)
