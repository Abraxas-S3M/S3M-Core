# fleetms Integration

S3M maintenance wrapper for [fleetms](https://github.com/jmnda-dev/fleetms).

## Military / Tactical Context

This adapter enables sovereign fleet sustainment planning by normalizing vehicle
service status, maintenance backlog visibility, and work-order context for
operational readiness decisions.

## Adapter Class

- `FleetmsAdapter`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- `integration_id = "fleetms"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.fleetms`

## Airgapped Behavior

In airgapped mode, `execute()` uses deterministic fixture data from:

- `fixtures/sample_response.json`

No external API calls are performed.
