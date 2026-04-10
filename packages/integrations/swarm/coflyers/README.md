# CoFlyers Integration

S3M swarm-domain adapter for **CoFlyers** (`https://github.com/micros-uav/CoFlyers`).

## Military / Tactical Context
This wrapper enables deterministic evaluation of cooperative motion algorithms
for coordinated UAV operations in contested or disconnected environments.

## Adapter Class
- `CoflyersAdapter`
- `integration_id = "coflyers"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.coflyers`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2/simulator runtime availability.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
