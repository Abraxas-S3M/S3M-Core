# Clermont Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Clermont command-center
dashboard operations used in readiness monitoring.

## Military/Tactical Context
Multi-view operational displays help commanders maintain common operating
pictures for personnel readiness and shift staffing in contested conditions.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Validation
`validate_availability()` checks configured local binary/path settings and
local command/runtime candidates for Clermont deployments.
