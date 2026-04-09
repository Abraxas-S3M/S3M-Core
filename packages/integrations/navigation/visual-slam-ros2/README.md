# visual-slam-ros2 Integration

## Purpose

This adapter wraps visual-slam-ros2 for visual-inertial localization readiness checks in S3M tactical navigation paths.

Military/tactical context: this wrapper helps operators confirm that
mission navigation pipelines remain deterministic and auditable on isolated
edge nodes before live deployment.

## Adapter Class

- `VisualSlamRos2Adapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.visual-slam-ros2`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local command/path availability for the wrapped stack

## Manifest

Integration metadata is stored in `manifest.yaml` and surfaced via `get_manifest()`.
