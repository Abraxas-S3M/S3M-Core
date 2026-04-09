# Evidently Dashboard Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Evidently monitoring output.

## Military/Tactical Context
Supports mission assurance by exposing model-quality regression and drift alerts
that operators can action before degraded AI behavior impacts operations.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- Dashboard flows remain deterministic with no outbound dependencies.

## Availability Checks
`validate_availability()` checks for local Evidently runtime availability and
uses fixture-presence checks in airgapped operation.

