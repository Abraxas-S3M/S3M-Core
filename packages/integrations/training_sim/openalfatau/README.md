# OpenAlfaTau Integration

## Purpose

This adapter wraps OpenAlfaTau tooling for S3M training and simulation workflows.

Military/tactical context: it enables scenario engineering teams to coordinate simulation assets and mission rehearsal state while preserving deterministic behavior in sovereign airgapped environments.

## Adapter Class

- `OpenalfatauAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.openalfatau`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture response from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path or available local runtime commands

## Manifest

Metadata is loaded from `manifest.yaml` by `get_manifest()`.
