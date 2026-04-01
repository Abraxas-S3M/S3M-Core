# Capella Provider Runbook

## Access and OAuth2 Setup
- Provider uses OAuth2 client credentials.
- Environment variables:
  - `S3M_CAPELLA_CLIENT_ID`
  - `S3M_CAPELLA_CLIENT_SECRET`

## SAR Operational Advantages
- X-band SAR supports day/night and cloud/smoke/sand penetration.
- Critical for Gulf operations where optical feeds are weather-limited.

## Collection Types
- `spotlight`: highest resolution (0.25m class).
- `stripmap`: wider-area coverage.
- `sliding_spotlight`: intermediate balance.

## Tactical S3M Usage
- Phase 15: maintain surveillance during sandstorms or night.
- Maritime surveillance: persistent ship and infrastructure observation.

## Saudi Gulf Focus
- Strait of Hormuz workflow supports high-priority monitoring lanes.
- Use SAR scenes for continuity when optical sources degrade.

## Air-Gapped Operations
- Cache catalog and tasking artifacts from connected enclave.
- Replay fixtures and cached outputs in offline runtime.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-capella/tests/ -v
```
