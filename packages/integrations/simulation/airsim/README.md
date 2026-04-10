# AirSim Integration

## Purpose

This adapter wraps the `AirSim` repository for S3M autonomous simulation workflows.

Military/tactical context: it provides deterministic telemetry snapshots for UAV mission rehearsal, enabling command teams to compare autonomy behavior under repeatable, sovereign airgapped conditions.

## Adapter Class

- `AirsimAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.airsim`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path and local Python module availability

## Manifest

`get_manifest()` loads integration metadata from `manifest.yaml`.
