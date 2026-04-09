# QGroundControl Integration

## Purpose

This adapter wraps the QGroundControl repository for S3M mission planning and autonomous UAV ground-control workflows.

Military/tactical context: it enables deterministic validation of sortie plans, geofences, and failsafe settings before upload in sovereign and disconnected command environments.

## Adapter Class

- `QgroundcontrolAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.qgroundcontrol`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
