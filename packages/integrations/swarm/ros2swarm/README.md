
# ROS2swarm Integration

## Purpose

This adapter wraps **ROS2swarm** for S3M swarm-domain mission workflows.

Military/tactical context: it enables sovereign operators to validate swarm
command behavior and simulation readiness in disconnected and contested
environments where external network calls are disallowed.

## Adapter Class

- `Ros2swarmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.ros2swarm`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture payload from
  `fixtures/sample_response.json`
- **Online mode**: performs local toolchain availability checks and returns
  orchestrator-governed runtime status

## Manifest

Metadata is declared in `manifest.yaml` and returned by `get_manifest()`.
