# BattleAgent Integration

S3M dashboard wrapper for [BattleAgent](https://github.com/agiresearch/BattleAgent), supporting battle emulation and planning dashboard workflows.

## Adapter Class

- `BattleagentAdapter` (`packages/integrations/dashboard/battleagent/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.dashboard.battleagent`

## Airgapped Operation

In airgapped mode, `execute()` returns fixture data from:

- `fixtures/sample_response.json`

This enables deterministic rehearsal of tactical planning pipelines without internet access.

## Online Availability Check

`validate_availability()` checks:

1. `BATTLEAGENT_PATH` / `S3M_BATTLEAGENT_PATH`
2. `battleagent` or `battle-agent` command availability

No external API calls are performed.

