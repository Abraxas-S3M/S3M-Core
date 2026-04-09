# OpenCTI Dashboard Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for OpenCTI dashboard telemetry.

## Military/Tactical Context
This adapter supports cyber command dashboards that track observables, campaign
activity, and mission risk scoring in sovereign or disconnected environments.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API traffic is required.

## Availability Checks
`validate_availability()` checks for local OpenCTI tooling (`pycti` module or
`opencti` binary). In airgapped mode, it verifies fixture presence.

