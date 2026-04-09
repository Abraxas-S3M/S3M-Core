# BattleSimulator Integration

S3M dashboard wrapper for [BattleSimulator](https://github.com/gregparkes/BattleSimulator), an animated 2D battle visualizer used for tactical behavior replay.

## Adapter Class

- `BattlesimulatorAdapter` (`packages/integrations/dashboard/battlesimulator/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.dashboard.battlesimulator`

## Airgapped Operation

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns fixture data from:

- `fixtures/sample_response.json`

This enables deterministic dashboard validation in sovereign, disconnected environments.

## Online Availability Check

`validate_availability()` checks:

1. `BATTLESIMULATOR_PATH` / `S3M_BATTLESIMULATOR_PATH` local path override
2. presence of `battlesimulator` or `battle-simulator` on `PATH`

No external API calls are performed.

