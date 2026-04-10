# BitsAndBytes Core Tooling Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [TimDettmers/bitsandbytes](https://github.com/TimDettmers/bitsandbytes).

## Military/Tactical Context
Supports sovereign edge deployment by validating memory-efficient quantization tooling so larger mission models can operate on constrained NVIDIA platforms without cloud dependence.

## Adapter Class
- `BitsandbytesAdapter` (`packages/integrations/core_tooling/bitsandbytes/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.core_tooling.bitsandbytes`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Checks
`validate_availability()` checks:
1. `BITSANDBYTES_PATH` / `S3M_BITSANDBYTES_PATH`
2. `BITSANDBYTES_BIN` / `S3M_BITSANDBYTES_BIN`
3. Python module presence (`bitsandbytes`)
4. Local command availability (`bitsandbytes`)
