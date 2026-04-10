# Unsloth Core Tooling Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [unslothai/unsloth](https://github.com/unslothai/unsloth).

## Military/Tactical Context
Supports rapid sovereign model adaptation by validating accelerated LoRA fine-tuning tooling on local NVIDIA infrastructure in airgapped operational environments.

## Adapter Class
- `UnslothAdapter` (`packages/integrations/core_tooling/unsloth/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.core_tooling.unsloth`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are made.

## Availability Checks
`validate_availability()` checks:
1. `UNSLOTH_PATH` / `S3M_UNSLOTH_PATH`
2. `UNSLOTH_BIN` / `S3M_UNSLOTH_BIN`
3. Python module presence (`unsloth`)
4. Local command availability (`unsloth`)
