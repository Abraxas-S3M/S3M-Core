# SC-LIO-SAM Integration

## Purpose

This adapter wraps SC-LIO-SAM to support LiDAR-inertial mapping readiness checks within S3M navigation workflows.

Military/tactical context: this wrapper helps operators confirm that
mission navigation pipelines remain deterministic and auditable on isolated
edge nodes before live deployment.

## Adapter Class

- `ScLioSamAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.sc-lio-sam`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/path availability for the wrapped stack

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via `get_manifest()`.
