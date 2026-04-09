# mav_multiagent_ws Integration

## Purpose

This adapter wraps the mav_multiagent_ws repository for S3M multi-UAV swarm coordination workflows.

Military/tactical context: it enables deterministic rehearsal of UAV task allocation and deconfliction logic so distributed aerial teams can be synchronized under disconnected command conditions.

## Adapter Class

- `MavMultiagentWsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.mav-multiagent-ws`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
