# GDELT Provider Runbook

## Registration and Credentials
- Provider: GDELT Project (OSINT / Global Events)
- Registration: none required (public API)
- Auth type: none

## API and Data Sources
- Doc API: `https://api.gdeltproject.org/api/v2/doc/doc`
- Geo API: `https://api.gdeltproject.org/api/v2/geo/geo`
- Daily CAMEO exports: `http://data.gdeltproject.org/events/{YYYYMMDD}.export.CSV.zip`

## CAMEO Reference Used in S3M
- `14*` protest
- `17*` coercion
- `18*` assault
- `19*` conflict/fighting
- `20*` mass violence

## GoldsteinScale Severity Mapping
- `< -7` -> `critical`
- `[-7, -3)` -> `high`
- `[-3, 0]` -> `medium`
- `> 0` -> `low`

## Query Construction Notes
- Keep Boolean query terms focused on tactical topics (Yemen conflict, Red Sea shipping, IRGC, UAV threats).
- Use 10 baseline Saudi-focused query bundles in `GDELTConfig.SAUDI_QUERIES` for repeatable monitoring.

## S3M Integration Notes
- Phase 19 IntelManager: ingest geocoded and media telemetry as near-real-time geopolitical heartbeat.
- Phase 11 GeopoliticalModule: consume CAMEO-coded conflict/protest/coercion trends.
- Phase 19 EarlyWarningSystem: use normalized conflict and tone shifts as indicator inputs.

## Air-Gapped Operation
- Pre-download daily CAMEO CSV export ZIPs on a connected node.
- Store extracted CSV and API snapshots under provider fixtures/cache paths.
- In `airgapped` mode, adapter reads local fixture data only (no egress).

## Smoke Test
```bash
python3 -m pytest packages/providers/osint-gdelt/tests/ -v
```
