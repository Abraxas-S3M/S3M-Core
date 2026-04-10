# crazyswarm (extensions) Integration

## Purpose

This adapter wraps `crazyswarm-extensions` for S3M swarm mission orchestration with deterministic,
airgapped execution paths.

Military/tactical context: command teams can validate multi-agent coordination
behaviors on isolated sovereign infrastructure before deployment in contested
communications environments.

## Adapter Class

- `CrazyswarmextensionsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.crazyswarm-extensions`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local ROS2/runtime availability only (no external API calls)

## Manifest

Metadata is maintained in `manifest.yaml` and exposed via `get_manifest()`.
