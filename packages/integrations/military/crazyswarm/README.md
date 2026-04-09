# Crazyswarm Integration

## Purpose

This adapter wraps the Crazyswarm repository for S3M multi-UAV swarm operations.

Military/tactical context: it enables deterministic rehearsal of synchronized drone-team maneuvers so operators can validate coordinated flight logic before live execution in contested airspace.

## Adapter Class

- `CrazyswarmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.crazyswarm`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
