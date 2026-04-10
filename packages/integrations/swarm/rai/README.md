# rai Integration

S3M swarm-domain adapter for **rai** (`https://github.com/RobotecAI/rai`).

## Military / Tactical Context
This wrapper supports deterministic validation of vendor-agnostic agentic ROS2
robotics orchestration for sovereign multi-domain mission execution.

## Adapter Class
- `RaiAdapter`
- `integration_id = "rai"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.rai`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local RAI/ROS2 runtime prerequisites.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
