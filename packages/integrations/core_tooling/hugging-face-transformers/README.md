# Hugging Face Transformers Integration

## Purpose

This adapter wraps Hugging Face Transformers so S3M can verify local LLM loading, tokenization, and fine-tuning readiness in sovereign environments.

Military/tactical context: it enables deterministic runtime validation for command-level language workflows on disconnected military networks.

## Adapter Class

- `HuggingFaceTransformersAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.core_tooling.hugging-face-transformers`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local module/binary checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
