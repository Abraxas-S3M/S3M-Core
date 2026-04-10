# Multi-Robot-Coordination-Framework Integration

## Purpose

This adapter wraps the `Multi-Robot-Coordination-Framework` repository for S3M swarm task-allocation workflows.

Military/tactical context: it enables deterministic rehearsal of fault-tolerant distributed task assignment so robotic teams can sustain patrol and logistics objectives when individual nodes fail.

## Adapter Class

- `MultiRobotCoordinationFrameworkAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.multi-robot-coordination-framework`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks for ROS2 and RL runtime toolchains

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.

