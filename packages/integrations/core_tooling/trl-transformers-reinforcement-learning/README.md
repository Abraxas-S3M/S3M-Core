# TRL (Transformers Reinforcement Learning) Integration

## Purpose

This adapter wraps TRL so S3M can validate local supervised fine-tuning and alignment readiness for training pipelines.

Military/tactical context: it supports controlled model alignment loops for command-language reliability in disconnected environments.

## Adapter Class

- `TrltransformersReinforcementLearningAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.core_tooling.trl-transformers-reinforcement-learning`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local module/binary checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
