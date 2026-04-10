# DroneSwarmGPT Integration

S3M swarm-domain wrapper for **DroneSwarmGPT**.

## Military / Tactical Context
This adapter supports rapid translation of mission intent into drone swarm plans
for tactical reconnaissance and perimeter control in high-tempo operations.

## Adapter Class
- `DroneswarmgptAdapter`
- `integration_id = "droneswarmgpt"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.droneswarmgpt`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` validates local runtime prerequisites only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
