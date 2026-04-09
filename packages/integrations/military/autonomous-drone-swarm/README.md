# autonomous-drone-swarm Integration

## Purpose

This adapter wraps the upstream `autonomous-drone-swarm` repository for S3M mission orchestration.

Military/tactical context: Wraps multi-agent RL swarm mapping pipelines to evaluate exploration behavior during tactical planning cycles.

## Adapter Class

- `AutonomousDroneSwarmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.autonomous-drone-swarm`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path readiness checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
