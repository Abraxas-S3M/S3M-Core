# Langfuse Dashboard Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Langfuse observability data.

## Military/Tactical Context
Enables mission AI reliability monitoring by summarizing trace behavior,
evaluation outcomes, and prompt drift indicators in command dashboards.

## Airgapped Behavior
- In `airgapped` mode, `execute()` serves `fixtures/sample_response.json`.
- This keeps observability dashboards operational in denied networks.

## Availability Checks
`validate_availability()` checks local Langfuse tooling (Python package or
binary) and uses fixture checks when running in airgapped mode.

