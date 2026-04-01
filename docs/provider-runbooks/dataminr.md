# Dataminr Provider Runbook

## Access and OAuth2
- OAuth2 client credential flow under contract.
- Environment variables:
  - `S3M_DATAMINR_CLIENT_ID`
  - `S3M_DATAMINR_CLIENT_SECRET`

## Real-Time Alerting Role
- Dataminr supplies rapid public-signal alerts for operational awareness.
- Alert tiers:
  - `flash` -> critical
  - `urgentAlert` -> high
  - `alert` -> medium

## S3M Watchlists
- `saudi_security`
- `gulf_maritime`
- `mena_military`
- `cyber_gcc`
- `red_sea_incidents`

## Tactical Use in S3M
- High-priority flash alerts feed immediate command attention.
- Supports near-real-time event awareness where other datasets lag.

## Air-Gapped Operations
- Export approved historical alert batches and watchlist metadata.
- Run fixture-backed workflows for deterministic mission rehearsal.

## Smoke Test
```bash
python3 -m pytest packages/providers/osint-dataminr/tests/ -v
```
