# Watcher Integration

S3M dashboard wrapper for [Watcher](https://github.com/thalesgroup-cert/Watcher), providing threat-hunting dashboard integration for anomaly triage workflows.

## Adapter Class

- `WatcherAdapter` (`packages/integrations/dashboard/watcher/adapter.py`)
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.dashboard.watcher`

## Airgapped Operation

When running in airgapped mode, `execute()` serves deterministic fixture data from:

- `fixtures/sample_response.json`

This allows repeatable cyber-defense dashboard exercises in disconnected enclaves.

## Online Availability Check

`validate_availability()` checks:

1. `WATCHER_PATH` / `S3M_WATCHER_PATH`
2. `watcher` or `watcher-cli` command presence

No external API calls are made by this adapter.

