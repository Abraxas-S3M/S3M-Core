# openrl Integration

S3M adapter for [OpenRL](https://github.com/OpenRL-Lab/openrl) in the autonomy domain.

## Tactical purpose

This wrapper supports unified RL experimentation for military single-agent and multi-agent mission profiles.

## Capabilities

- Wrapper metadata and execution through the common `IntegrationAdapter` contract
- Local package availability validation for `openrl`
- Airgapped fixture execution path for deterministic, sovereign environments

## Airgapped behavior

When running in airgapped mode, the adapter returns `fixtures/sample_response.json` to emulate primary training outputs.
