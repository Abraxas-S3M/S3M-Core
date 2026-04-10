# Fleetbase Maintenance Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Fleetbase in the Procurement & Maintenance domain.

## Military/Tactical Context
Supports sustainment command cells with offline-ready fleet maintenance snapshots, helping planners preserve mission-ready platforms under denied-network conditions.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks a configured local path (`FLEETBASE_PATH`) or local module/CLI presence.
