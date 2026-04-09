# Phoenix Dashboard Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Phoenix tracing dashboards.

## Military/Tactical Context
Supports mission AI validation workflows by exposing LLM trace quality,
experiment regressions, and policy-guardrail outcomes in one local dashboard.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external services are contacted.

## Availability Checks
`validate_availability()` verifies local Phoenix tooling and uses fixture checks
for offline/airgapped operation.

