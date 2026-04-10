# Langostino Integration

S3M swarm-domain wrapper for **Langostino**.

## Military / Tactical Context
This adapter supports ROS2-based autonomous drone control rehearsal for tactical
surveillance and maneuver coordination in disconnected operations.

## Adapter Class
- `LangostinoAdapter`
- `integration_id = "langostino"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.langostino`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2/runtime prerequisites only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
