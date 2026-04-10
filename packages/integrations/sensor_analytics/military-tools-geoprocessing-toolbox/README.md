# military-tools-geoprocessing-toolbox Integration

## Purpose

This adapter wraps the Esri military geoprocessing toolbox for S3M sensor analytics workflows.

Military/tactical context: it supports terrain and intelligence-product generation used by command staffs for movement planning, reconnaissance overlays, and operational rehearsal.

## Adapter Class

- `MilitaryToolsGeoprocessingToolboxAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.military-tools-geoprocessing-toolbox`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: validates local geoprocessing tool dependencies and returns readiness metadata

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
