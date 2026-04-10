# NLP-Arabic-text-summarization-using-araBART Integration

## Purpose

This adapter wraps the `NLP-Arabic-text-summarization-using-araBART` repository for secure communications workflows in S3M.

Military/tactical context: it supports resilient mission communications by enforcing local validation and deterministic fixture-based behavior when disconnected from external networks.

## Adapter Class

- `NlpArabicTextSummarizationAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.comms.nlp-arabic-text-summarization-using-arab`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local toolchain availability and returns orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
