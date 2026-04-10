# Synthea Simulation Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [Synthea](https://github.com/synthetichealth/synthea) in the Simulation domain.

## Military/Tactical Context
This adapter helps planning cells rehearse contested-environment casualty surges and sustainment demand using synthetic population outputs while disconnected from external services.

## Adapter Class
- `SyntheaAdapter` (`packages/integrations/simulation/synthea/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.synthea`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `SYNTHEA_PATH` / `S3M_SYNTHEA_PATH`
2. `SYNTHEA_JAR` / `S3M_SYNTHEA_JAR`
3. Local command availability (`synthea`, `java`)
