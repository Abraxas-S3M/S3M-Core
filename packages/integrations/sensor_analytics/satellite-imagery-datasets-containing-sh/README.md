# Satellite-Imagery-Datasets-Containing-Ships Integration

## Purpose

This adapter wraps the
[Satellite-Imagery-Datasets-Containing-Ships](https://github.com/jasonmanesis/Satellite-Imagery-Datasets-Containing-Ships)
repository for S3M sensor analytics workflows.

Military/tactical context: commanders need a vetted catalog of maritime remote
sensing datasets so ship-detection models can be trained and validated on
sovereign infrastructure without internet dependency.

## Adapter Class

- `SatelliteImageryDatasetsContainingAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.satellite-imagery-datasets-containing-sh`

## Operational Modes

- **Airgapped mode**: `execute()` returns deterministic fixture data from
  `fixtures/sample_response.json`.
- **Online mode**: validates only local tooling/path availability; no external
  API calls are made.

## Manifest

Integration metadata is stored in `manifest.yaml` and returned by
`get_manifest()`.
