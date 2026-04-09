# ros-voice-assistant Integration

## Purpose

This adapter wraps the ros-voice-assistant repository for S3M voice-enabled ROS2 robotic applications.

Military/tactical context: it supports hands-free tactical command and spoken acknowledgement loops so operators can maintain focus on battlefield telemetry while directing robotic assets.

## Adapter Class

- `RosVoiceAssistantAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.hmi.ros-voice-assistant`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
