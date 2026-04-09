# ROS2-NMPC-ACADOS Integration

## Purpose

This adapter wraps the upstream **ROS2-NMPC-ACADOS** repository for S3M navigation and control workflows.

Military/tactical context: it enables deterministic mission rehearsal outputs for route control and vehicle deconfliction when units must operate in disconnected, airgapped, or GPS-stressed conditions.

## Adapter Class

- `Ros2NmpcAcadosAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.ros2-nmpc-acados`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/module availability and returns runtime handoff status

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
