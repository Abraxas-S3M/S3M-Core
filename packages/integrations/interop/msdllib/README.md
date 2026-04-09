# msdllib Integration

## Purpose

This adapter wraps the `msdllib` repository for S3M MSDL parsing and simulation-input preparation workflows.

Military/tactical context: it supports deterministic validation of force-structure and scenario-definition data before rehearsal systems execute mission plans.

## Adapter Class

- `MsdllibAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.msdllib`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local toolchain checks with no external API calls

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
