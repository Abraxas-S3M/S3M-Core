# Langfuse HMI Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Langfuse in the Human-Machine Teaming domain.

## Military/Tactical Context
Supports mission assurance teams with local trace observability, evaluation monitoring, and prompt governance for LLM-enabled decision support systems.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks for a local Langfuse Python module or CLI binary and falls back to fixture validation in airgapped mode.
