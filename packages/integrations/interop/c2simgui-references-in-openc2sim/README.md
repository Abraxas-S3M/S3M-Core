# C2SIMGUI (references in OpenC2SIM) Integration

## Purpose

This adapter wraps C2SIMGUI reference components found in OpenC2SIM repositories for S3M interoperability workflows.

Military/tactical context: it supports battle-staff dashboard rehearsals by preserving deterministic command-and-control visualization behavior in disconnected environments.

## Adapter Class

- `C2simguireferencesInOpenc2simAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.c2simgui-references-in-openc2sim`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime validation before orchestration handoff

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
