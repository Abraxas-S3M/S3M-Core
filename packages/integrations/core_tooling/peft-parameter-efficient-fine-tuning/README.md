# PEFT (Parameter-Efficient Fine-Tuning) Integration

## Purpose

This adapter wraps PEFT so S3M can validate local parameter-efficient fine-tuning readiness on sovereign datasets.

Military/tactical context: it supports adaptation of mission language models with controlled compute budgets and strict data residency.

## Adapter Class

- `PeftparameterEfficientFineAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.core_tooling.peft-parameter-efficient-fine-tuning`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local module/binary checks only (no external API calls)

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
