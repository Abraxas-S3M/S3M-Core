# multi-agent-reinforcement-learning-active-slam Integration

S3M swarm-domain adapter for **multi-agent-reinforcement-learning-active-slam** (`https://github.com/i1Cps/multi-agent-reinforcement-learning-active-slam`).

## Military / Tactical Context
This adapter supports deterministic active-SLAM workflow checks for distributed
scout teams generating maps and exploration plans in denied communications
environments.

## Adapter Class
- `MultiAgentReinforcementLearningAdapter`
- `integration_id = "multi-agent-reinforcement-learning-activ"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.multi-agent-reinforcement-learning-activ`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2/SLAM runtime hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
