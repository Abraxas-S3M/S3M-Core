# ray (with RLlib) Integration

S3M adapter for [Ray RLlib](https://github.com/ray-project/ray) in the autonomy domain.

## Tactical purpose

This wrapper supports distributed reinforcement-learning rehearsal for military swarm behaviors in contested environments.

## Capabilities

- Distributed policy training for multi-agent teams
- Airgapped execution using local fixture data
- Local runtime validation for `ray` and `ray.rllib`

## Airgapped behavior

When `mode="airgapped"` or `S3M_AIRGAPPED=true`, `execute()` returns `fixtures/sample_response.json` so mission pipelines remain deterministic without network access.
