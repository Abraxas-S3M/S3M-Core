# openbw Integration

## Purpose

This adapter wraps the OpenBW repository for S3M training and simulation workflows.

Military/tactical context: it supports deterministic rehearsal of force movement, engagement timing, and scenario replay under sovereign airgapped constraints.

## Adapter Class

- `OpenbwAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.openbw`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from `fixtures/sample_response.json`
- **Online mode**: validates local binary/path configuration and reports readiness

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
