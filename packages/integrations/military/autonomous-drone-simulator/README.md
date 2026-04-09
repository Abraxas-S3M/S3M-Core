# autonomous_drone_simulator Integration

## Purpose

This adapter wraps the upstream `autonomous_drone_simulator` repository for S3M mission orchestration.

Military/tactical context: Enables swarm mission rehearsal to stress-test autonomy policies before field deployment in high-risk sectors.

## Adapter Class

- `AutonomousDroneSimulatorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.autonomous-drone-simulator`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path readiness checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
