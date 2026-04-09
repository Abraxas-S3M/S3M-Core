# multirotor_launch (West Point) Integration

## Purpose

This adapter wraps the West Point `multirotor_launch` repository for S3M mission
orchestration pipelines that stage ROS launch plans for multirotor UAV control.

Military/tactical context: the wrapper gives commanders a deterministic way to
rehearse launch procedures for reconnaissance flights in disconnected or
electromagnetically contested operating environments.

## Adapter Class

- `MultirotorLaunchwestPointAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.multirotor-launch-west-point`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local ROS command/path checks with orchestrator-ready output

## Manifest

Integration metadata is stored in `manifest.yaml` and returned by `get_manifest()`.
