# Awesome-Remote-Sensing Integration

## Purpose

This adapter wraps curated remote sensing resource catalogs for S3M analyst workflows.

Military/tactical context: it supports rapid mission analytics setup by surfacing vetted references for satellite processing, change detection, and ISR pipeline design in disconnected environments.

## Adapter Class

- `AwesomeRemoteSensingAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.sensor_analytics.awesome-remote-sensing`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: validates local catalog/tool access and returns readiness metadata

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
