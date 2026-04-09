# by_your_command Integration

## Purpose

This adapter wraps the by_your_command repository for S3M ROS2 voice-command workflows.

Military/tactical context: it enables spoken tactical directives with optional camera context so robotic teammates can be tasked quickly in high-tempo operations.

## Adapter Class

- `ByYourCommandAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.hmi.by-your-command`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
