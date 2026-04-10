# open-msupply Maintenance Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for open-msupply in the Procurement & Maintenance domain.

## Military/Tactical Context
Supports sustainment planning by exposing deterministic stock and serviceability summaries used for mission continuity decisions in airgapped theaters.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks a configured local path (`OPEN_MSUPPLY_PATH`) or local module/CLI presence.
