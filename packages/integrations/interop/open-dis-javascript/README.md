# open-dis-javascript Integration

## Purpose

This adapter wraps open-dis JavaScript components for S3M Interoperability & Simulation workflows.

Military/tactical context: it enables command-post simulation teams to standardize DIS message handling and coordinate transforms during disconnected mission rehearsal.

## Adapter Class

- `OpenDisJavascriptAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.open-dis-javascript`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime validation before orchestration handoff

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
