# SimpleC2Sim Integration

## Purpose

This adapter wraps the SimpleC2Sim repository for S3M low-fidelity command-and-control simulation rehearsal.

Military/tactical context: it enables rapid operator drill cycles in disconnected conditions where deterministic replay and controlled validation are essential.

## Adapter Class

- `Simplec2simAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.simplec2sim`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime/path checks with no external API dependency

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
