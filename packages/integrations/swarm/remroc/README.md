# remroc Integration

## Purpose

This adapter wraps the `remroc` repository for S3M swarm-domain simulation workflows.

Military/tactical context: it enables deterministic rehearsal of coordinated ground-robot maneuvers for route clearance and perimeter screening before live deployment in denied or degraded environments.

## Adapter Class

- `RemrocAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.remroc`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks for ROS2/Gazebo-style toolchains

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.

