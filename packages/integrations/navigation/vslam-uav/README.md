# VSLAM-UAV Integration

## Purpose

This adapter wraps VSLAM-UAV to expose PX4+Isaac ROS visual navigation readiness on Jetson platforms in S3M.

Military/tactical context: this wrapper helps operators confirm that
mission navigation pipelines remain deterministic and auditable on isolated
edge nodes before live deployment.

## Adapter Class

- `VslamUavAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.vslam-uav`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/path availability for the wrapped stack

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via `get_manifest()`.
