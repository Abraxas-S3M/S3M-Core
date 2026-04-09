# Fleetbase Integration

S3M dashboard wrapper for [Fleetbase](https://github.com/fleetbase/fleetbase), focused on logistics and sustainment observability for military operations.

## Adapter Class

- `FleetbaseAdapter` (`packages/integrations/dashboard/fleetbase/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.dashboard.fleetbase`

## Airgapped Operation

In airgapped mode, `execute()` returns fixture data from:

- `fixtures/sample_response.json`

This allows deterministic logistics dashboard behavior in sovereign disconnected deployments.

## Online Availability Check

`validate_availability()` checks:

1. `FLEETBASE_PATH` / `S3M_FLEETBASE_PATH`
2. `fleetbase` or `fleetbase-cli` command availability

No external API calls are executed.

