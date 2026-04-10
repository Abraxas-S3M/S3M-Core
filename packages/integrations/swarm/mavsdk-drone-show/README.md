# mavsdk_drone_show Integration

## Purpose

This adapter wraps the `mavsdk_drone_show` repository for S3M PX4 swarm mission-control workflows.

Military/tactical context: it enables deterministic rehearsal of synchronized leader-follower UAV behaviors and SAR support patterns before live sorties in contested operational zones.

## Adapter Class

- `MavsdkDroneShowAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.mavsdk-drone-show`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks for MAVSDK/PX4 runtime tooling

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.

