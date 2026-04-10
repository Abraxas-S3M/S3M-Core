# UAV-orchestrator Integration

## Purpose

This adapter wraps the `UAV-orchestrator` repository for S3M swarm mission orchestration workflows.

Military/tactical context: it enables deterministic rehearsal of UAV team orchestration, including airborne task balancing and charging logistics, before live operations in contested airspace.

## Adapter Class

- `UavOrchestratorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.uav-orchestrator`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local dependency checks for orchestration runtime components

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.

