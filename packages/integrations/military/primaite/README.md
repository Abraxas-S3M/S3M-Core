# PrimAITE integration

S3M military integration wrapper for
[PrimAITE](https://github.com/Autonomous-Resilient-Cyber-Defence/PrimAITE).

## Military/Tactical context

This adapter enables sovereign orchestration of AI cyber-defense training runs
for military networks, including deterministic rehearsal outputs in airgapped
environments.

## Adapter contract

- Class: `PrimaiteAdapter`
- Base class: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.military.primaite`

## Behavior

- Loads metadata from `manifest.yaml`
- Validates local runtime availability
- Returns fixture-backed responses in airgapped mode
- Performs no external API calls
