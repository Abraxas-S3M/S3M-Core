# Swarm-Formation Integration

S3M swarm-domain adapter for **Swarm-Formation** (`https://github.com/ZJU-FAST-Lab/Swarm-Formation`).

## Military / Tactical Context
This wrapper enables deterministic assessment of distributed formation-flight
optimization in dense terrain for coordinated surveillance and strike support.

## Adapter Class
- `SwarmFormationAdapter`
- `integration_id = "swarm-formation"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.swarm-formation`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local trajectory-planning runtime prerequisites.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
