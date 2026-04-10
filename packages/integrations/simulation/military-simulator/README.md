# Military-Simulator Integration

## Purpose

This adapter wraps the Military-Simulator repository for S3M simulation and war-gaming workflows.

Military/tactical context: it provides deterministic offline outputs and local availability checks so command planners can assess tactical courses of action in disconnected sovereign environments.

## Adapter Class

- `MilitarySimulatorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.military-simulator`

## Operational Modes

- **Airgapped mode**: fixture replay from `fixtures/sample_response.json`
- **Online mode**: runtime/tool presence checks with standardized status response

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
