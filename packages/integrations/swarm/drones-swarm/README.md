# drones-swarm Integration

## Purpose

This adapter wraps the `drones-swarm` repository for S3M adaptive exploration and tracking workflows.

Military/tactical context: it enables deterministic rehearsal of distributed UAV search and tracking missions to validate coverage and contact continuity before field operations.

## Adapter Class

- `DronesSwarmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.drones-swarm`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime checks for drone swarm simulation dependencies

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.

