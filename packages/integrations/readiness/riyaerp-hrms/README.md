# RiyaErp-hrms Integration

S3M wrapper for the [RiyaErp-hrms](https://github.com/TheLogicIraqCompany/RiyaErp-hrms) repository.

## Military/Tactical Context

This adapter transforms HR and payroll records into operational personnel
readiness indicators so commanders can monitor deployability and sustainment
under sovereign, offline deployment constraints.

## Behavior

- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks configured local path or runtime hints.
- `execute()` returns `fixtures/sample_response.json` in airgapped mode.
- Online mode returns local readiness status only and avoids network calls.

## Adapter Class

- Module: `packages.integrations.readiness.riyaerp-hrms.adapter`
- Class: `RiyaerpHrmsAdapter`
- Integration ID: `riyaerp-hrms`
- Domain: `readiness`
