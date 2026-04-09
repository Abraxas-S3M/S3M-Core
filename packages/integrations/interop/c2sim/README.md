# c2sim Integration

## Purpose

This adapter wraps the GMU `c2sim` repository for S3M interoperability validation workflows.

Military/tactical context: it supports command-post rehearsals where message schema and semantic checks must complete offline before coalition deployment.

## Adapter Class

- `C2simAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.c2sim`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime/toolchain availability checks only

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
