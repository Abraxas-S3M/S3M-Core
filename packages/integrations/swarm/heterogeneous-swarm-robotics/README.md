# heterogeneous-swarm-robotics Integration

S3M swarm-domain adapter for **heterogeneous-swarm-robotics** (`https://github.com/nema-oss/heterogeneous-swarm-robotics`).

## Military / Tactical Context
This adapter supports resilience assessment of mixed robot fleets to help
mission planners evaluate continuity under attrition, communication stress, and
dynamic retasking requirements in sovereign offline environments.

## Adapter Class
- `HeterogeneousSwarmRoboticsAdapter`
- `integration_id = "heterogeneous-swarm-robotics"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.heterogeneous-swarm-robotics`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries, modules, and configured paths.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
