# Phoenix HMI Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for Phoenix in the Human-Machine Teaming domain.

## Military/Tactical Context
Supports tactical AI assurance by summarizing experiment outcomes, trace anomalies, and evaluation quality for mission-support models.

## Airgapped Behavior
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks for local Phoenix Python modules or CLI binaries and uses fixture validation in airgapped mode.
