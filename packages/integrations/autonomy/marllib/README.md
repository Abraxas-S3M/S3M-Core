# MARLlib Integration

S3M adapter for [MARLlib](https://github.com/Replicable-MARL/MARLlib) in the autonomy domain.

## Tactical purpose

This wrapper enables coordinated multi-agent RL experimentation for military swarm and escort mission scenarios.

## Capabilities

- Unified `execute()` wrapper for MARL workflows
- Availability checks for `marllib` and Ray RLlib components
- Deterministic airgapped fixture returns for sovereign deployments

## Airgapped behavior

Airgapped mode returns `fixtures/sample_response.json` so tactical pipelines can run without external dependencies.
