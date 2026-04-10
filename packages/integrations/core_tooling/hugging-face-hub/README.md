# Hugging Face Hub Integration

## Purpose

This adapter wraps Hugging Face Hub tooling so S3M can verify offline model cache and artifact staging readiness on sovereign infrastructure.

Military/tactical context: it supports controlled prepositioning of approved model artifacts for disconnected operational theaters.

## Adapter Class

- `HuggingFaceHubAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.core_tooling.hugging-face-hub`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/module checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
