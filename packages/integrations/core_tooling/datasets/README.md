# Datasets Core Tooling Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [huggingface/datasets](https://github.com/huggingface/datasets).

## Military/Tactical Context
Supports sovereign training-data operations by validating local dataset ingestion and transformation tooling for classified/offline corpus preparation in airgapped environments.

## Adapter Class
- `DatasetsAdapter` (`packages/integrations/core_tooling/datasets/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.core_tooling.datasets`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Checks
`validate_availability()` checks:
1. `DATASETS_PATH` / `S3M_DATASETS_PATH`
2. `DATASETS_BIN` / `S3M_DATASETS_BIN`
3. Python module presence (`datasets`)
4. Local command availability (`datasets-cli`)
