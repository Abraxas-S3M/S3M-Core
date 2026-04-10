# Accelerate Core Tooling Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [huggingface/accelerate](https://github.com/huggingface/accelerate).

## Military/Tactical Context
Supports sovereign model-training readiness by validating local distributed and mixed-precision tooling so command AI workloads can be tuned inside disconnected defense infrastructure.

## Adapter Class
- `AccelerateAdapter` (`packages/integrations/core_tooling/accelerate/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.core_tooling.accelerate`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Checks
`validate_availability()` checks:
1. `ACCELERATE_PATH` / `S3M_ACCELERATE_PATH`
2. `ACCELERATE_BIN` / `S3M_ACCELERATE_BIN`
3. Python module presence (`accelerate`)
4. Local command availability (`accelerate`)
