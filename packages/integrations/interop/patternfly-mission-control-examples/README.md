# patternfly (mission-control examples) Integration

## Purpose

This adapter wraps PatternFly mission-control example assets for S3M Interoperability & Simulation workflows.

Military/tactical context: it supports deterministic operator dashboard rehearsals for force tracking and command-and-control decision cycles during communications-constrained operations.

## Adapter Class

- `PatternflymissionControlExamplesAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.interop.patternfly-mission-control-examples`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime validation before orchestration handoff

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
