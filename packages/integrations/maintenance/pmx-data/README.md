# pmx_data Maintenance Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for pmx_data in the Procurement & Maintenance domain.

## Military/Tactical Context
Supports mission sustainment analytics by exposing deterministic predictive-maintenance dataset summaries that can be consumed by local readiness models.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks a configured local path (`PMX_DATA_PATH`) or local module/CLI presence.
