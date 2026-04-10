# satellite-jamming-simulator Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [satellite-jamming-simulator](https://github.com/deptofdefense/satellite-jamming-simulator(archived) in the Simulation domain.

## Military/Tactical Context
This adapter supports electronic-warfare mission rehearsal by modeling earth-to-space RF jamming impacts on SATCOM links while fully disconnected from external networks.

## Adapter Class
- `SatelliteJammingSimulatorAdapter` (`packages/integrations/simulation/satellite-jamming-simulator/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.simulation.satellite-jamming-simulator`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `SATELLITE_JAMMING_SIMULATOR_PATH` / `S3M_SATELLITE_JAMMING_SIMULATOR_PATH`
2. `SATELLITE_JAMMING_SIMULATOR_ENTRYPOINT` / `S3M_SATELLITE_JAMMING_SIMULATOR_ENTRYPOINT`
3. Local command availability (`satellite-jamming-simulator`, `sat-jam-sim`)
