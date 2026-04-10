# learnhouse Readiness Integration

## Purpose
Provides an S3M `IntegrationAdapter` wrapper for [learnhouse](https://github.com/learnhouse/learnhouse) training and certification tracking.

## Military/Tactical Context
Supports command readiness by tracking tactical course progression and certification currency to identify capability gaps before deployment.

## Adapter Class
- `LearnhouseAdapter` (`packages/integrations/readiness/learnhouse/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.readiness.learnhouse`

## Airgapped Operation
- In `airgapped` mode, `execute()` returns `fixtures/sample_response.json`.
- No external API calls are performed.

## Availability Checks
`validate_availability()` checks:
1. `LEARNHOUSE_PATH` / `S3M_LEARNHOUSE_PATH`
2. Local command availability (`learnhouse`, `docker`, `node`, `npm`)
