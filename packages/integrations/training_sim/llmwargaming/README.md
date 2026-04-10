# LLMWargaming Integration

## Purpose

This adapter wraps the upstream **LLMWargaming** repository for S3M training and simulation workflows.

Military/tactical context: it provides deterministic course-of-action rehearsal outputs for mission planning cells operating in disconnected, sovereign environments.

## Adapter Class

- `LlmwargamingAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.llmwargaming`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local tooling and returns runtime readiness status

## Manifest

Metadata is stored in `manifest.yaml` and loaded by `get_manifest()`.
