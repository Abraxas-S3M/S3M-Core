# Autonomous-Ai-drone-scripts Integration

## Purpose

This adapter wraps the upstream `Autonomous-Ai-drone-scripts` repository for S3M mission orchestration.

Military/tactical context: Provides autonomous route-following and obstacle evasion to keep multirotor assets survivable in denied environments.

## Adapter Class

- `AutonomousAiDroneScriptsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.autonomous-ai-drone-scripts`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path readiness checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
