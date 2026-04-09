# Autonomous-drone-navigation Integration

## Purpose

This adapter wraps Autonomous-drone-navigation to validate indoor UAV fusion-stack readiness for S3M mission control.

Military/tactical context: this wrapper helps operators confirm that
mission navigation pipelines remain deterministic and auditable on isolated
edge nodes before live deployment.

## Adapter Class

- `AutonomousDroneNavigationAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.autonomous-drone-navigation`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/path availability for the wrapped stack

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via `get_manifest()`.
