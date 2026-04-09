# drone_path_predictor_ros Integration

## Purpose

This adapter wraps the upstream **drone_path_predictor_ros** repository for S3M navigation and control workflows.

Military/tactical context: it enables deterministic mission rehearsal outputs for route control and vehicle deconfliction when units must operate in disconnected, airgapped, or GPS-stressed conditions.

## Adapter Class

- `DronePathPredictorRosAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.drone-path-predictor-ros`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/module availability and returns runtime handoff status

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
