# multiRobotExploration-RobotArmy Integration

## Purpose

This adapter wraps the upstream `multiRobotExploration-RobotArmy` repository for S3M mission orchestration.

Military/tactical context: Coordinates UAV and UGV exploration patrols so reconnaissance teams can map contested zones while reducing operator workload.

## Adapter Class

- `MultirobotexplorationRobotarmyAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.multirobotexploration-robotarmy`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path readiness checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
