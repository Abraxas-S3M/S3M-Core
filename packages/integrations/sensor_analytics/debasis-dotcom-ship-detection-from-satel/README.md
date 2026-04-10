# debasis-dotcom/Ship-Detection-from-Satellite-Images-using-YOLOV4 Integration

## Purpose

This adapter wraps YOLOv4 ship-detection workflows for S3M satellite analytics.

Military/tactical context: it supports maritime situational awareness by identifying vessel contacts in overhead imagery for cueing patrol routes and threat-assessment cells.

## Adapter Class

- `DebasisDotcomshipDetectionFromAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.debasis-dotcom-ship-detection-from-satel`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: validates local ship-detection prerequisites and returns readiness metadata

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
