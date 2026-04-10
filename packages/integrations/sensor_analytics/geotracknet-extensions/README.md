# GeoTrackNet extensions Integration

## Purpose

This adapter wraps GeoTrackNet extension workflows for S3M maritime remote sensing analytics.

Military/tactical context: it supports anomaly triage for AIS vessel tracks with satellite corroboration to improve interdiction tasking and patrol prioritization in contested waters.

## Adapter Class

- `GeotracknetExtensionsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.geotracknet-extensions`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: validates local GeoTrackNet prerequisites and returns readiness metadata

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
