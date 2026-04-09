# LLM_ROS2 Integration

## Purpose

This adapter wraps the LLM_ROS2 repository for S3M multimodal conversational robotics workflows.

Military/tactical context: it supports operator-to-robot dialogue grounded in camera and LiDAR sensing to improve tasking speed and route safety under battlefield constraints.

## Adapter Class

- `LlmRos2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.hmi.llm-ros2`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
