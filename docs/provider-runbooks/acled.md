# ACLED Provider Runbook

## Provider Name and Category

- Provider: ACLED
- Category: OSINT Global Events

## Official API Documentation URL

- URL: https://acleddata.com/acled-api-documentation/

## Registration and Authentication

1. Register a research account with ACLED.
2. Request API access credentials (key + account email).
3. Configure environment variables:
   - `S3M_ACLED_API_KEY`
   - `S3M_ACLED_EMAIL`

Auth model: API key and email query parameters.

## Event Taxonomy and Reliability Notes

- Core event types used in S3M:
  - Battles
  - Explosions/Remote violence
  - Violence against civilians
  - Protests
  - Riots
  - Strategic developments
- ACLED fatality counts are treated as ground-truth input for escalation logic.
- `geo_precision` maps to confidence:
  - 1 -> 0.95 (exact)
  - 2 -> 0.8 (near)
  - 3 -> 0.6 (approximate)

## Rate Limits and Quotas

- S3M configured rate: 5 RPM
- ACLED daily budget target: 500 requests/day

## S3M Integration Context

- Phase 19 EarlyWarningSystem:
  - Fatality-heavy Yemen events directly increase escalation indicators.
- Phase 11 GeopoliticalModule:
  - Verified casualties and actor identity improve regional risk scoring.
- Phase 19 CrisisTracker:
  - Repeated high-fatality clusters are prioritized for incident tracking.

## Air-Gapped Operations

- Tactical context: disconnected deployments still need verifiable conflict baselines.
- Air-gapped adapter mode reads:
  - `packages/providers/osint-acled/fixtures/acled_mena_response.json`
- Periodically export approved ACLED snapshots from a connected enclave and import to local fixture/cache storage.

## Smoke Test

```bash
python3 -m pytest packages/providers/osint-acled/tests/ -v
```
