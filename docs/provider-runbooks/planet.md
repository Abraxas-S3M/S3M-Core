# Planet Provider Runbook

## Contract and Context
- Planet supports daily global monitoring and tasking.
- NATO APSS context makes this provider operationally relevant for coalition workflows.
- Environment variable:
  - `S3M_PLANET_API_KEY`

## Authentication
- Basic auth API key pattern (`username=key`, empty password).

## Product Types
- PlanetScope (PSScene): 3m daily coverage.
- SkySat: 0.5m taskable collection.
- Pelican: 0.4m taskable collection.

## Daily Coverage Model
- Use `search_daily_coverage` to answer whether recent imagery exists for mission AOI.
- This is the tactical baseline for persistent monitoring.

## Tasking and Orders
- Search candidate scenes.
- Submit order for bundle (`analytic_udm2`, `visual`, `analytic_sr`).
- Submit SkySat tasking for high-priority requests.

## Basemaps and Change Detection
- Basemap mosaics provide cloud-reduced temporal context.
- Supports Phase 19 change detection and long-baseline comparison.

## S3M Integration
- Phase 15: daily scene refresh for wide-area monitoring.
- Phase 19: trend and change baselining from recurring Planet coverage.

## Air-Gapped Operations
- Export approved scene metadata and derivative products.
- Move artifacts into offline store for deterministic replay.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-planet/tests/ -v
```
