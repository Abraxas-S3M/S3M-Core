# Explainerdashboard HMI Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Explainerdashboard in the Human-Machine Teaming domain.

## Military/Tactical Context
Supports mission AI transparency by exposing feature-level explanations and prediction audits used in commander decision briefings.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks for a local Explainerdashboard Python module or CLI binary and uses fixture validation in airgapped mode.
