# MoveIt (motion planning) Integration

## Purpose

This adapter wraps **MoveIt** for S3M navigation and motion-control workflows.

Military/tactical context: it supports deterministic maneuver planning checks for robotic platforms that must operate in obstacle-dense and communications-constrained theaters.

## Adapter Class

- `MoveitmotionPlanningAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.moveit-motion-planning`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local MoveIt/ROS runtime checks without external API calls

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
