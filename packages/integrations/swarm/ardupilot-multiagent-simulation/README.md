# Ardupilot_Multiagent_Simulation Integration

S3M swarm-domain wrapper for **Ardupilot_Multiagent_Simulation**.

## Military / Tactical Context
This adapter supports mission rehearsal and formation validation in simulation
before live deployment of autonomous multi-UAV teams.

## Adapter Class
- `ArdupilotMultiagentSimulationAdapter`
- `integration_id = "ardupilot-multiagent-simulation"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.ardupilot-multiagent-simulation`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local simulation dependencies only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
