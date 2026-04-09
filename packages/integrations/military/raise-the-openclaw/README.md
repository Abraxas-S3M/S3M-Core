# Raise-The-OpenClaw integration

S3M military integration wrapper for
[Raise-The-OpenClaw](https://github.com/bgoldmann/Raise-The-OpenClaw).

## Military/Tactical context

This adapter standardizes mission-orchestration checks for Army-style autonomous
agent meshes so commanders can rehearse distributed AI behavior in sovereign,
airgapped environments.

## Adapter contract

- Class: `RaiseTheOpenclawAdapter`
- Base class: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.military.raise-the-openclaw`

## Behavior

- Loads metadata from `manifest.yaml`
- Validates local runtime availability via binary/path checks
- Returns deterministic fixture data in airgapped mode
- Avoids external API calls
