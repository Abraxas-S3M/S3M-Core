# SamGeo (segment-geospatial extensions) Integration

## Purpose

This adapter wraps SamGeo extension workflows for S3M remote sensing segmentation pipelines.

Military/tactical context: it provides deterministic object-mask extraction support for reconnaissance, coastal surveillance, and mission rehearsal in airgapped command environments.

## Adapter Class

- `SamgeosegmentGeospatialExtensionsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.samgeo-segment-geospatial-extensions`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: validates local SamGeo prerequisites and returns readiness metadata

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
