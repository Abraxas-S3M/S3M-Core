# ModelStudio HMI Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for ModelStudio in the Human-Machine Teaming domain.

## Military/Tactical Context
Supports mission-readiness reviews by exposing model behavior, residual risks, and what-if analysis needed for commander trust in AI-enabled planning.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks local Python/R tooling relevant to ModelStudio workflows and uses fixture validation in airgapped mode.
