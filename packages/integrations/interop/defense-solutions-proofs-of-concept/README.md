# defense-solutions-proofs-of-concept Integration

## Purpose

This adapter wraps Esri defense solutions proof-of-concept assets for S3M interoperability workflows.

Military/tactical context: it supports deterministic rehearsal of Air C2 COP and tactical mapping workflows for command elements operating in disconnected environments.

## Adapter Class

- `DefenseSolutionsProofsOfAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.defense-solutions-proofs-of-concept`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime validation before orchestration handoff

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
