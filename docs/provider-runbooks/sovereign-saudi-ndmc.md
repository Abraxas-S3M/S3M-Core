# Sovereign Saudi NDMC Runbook

## Government Relationship
Saudi National Center of Meteorology (NCM) operates under the Ministry of Environment, Water and Agriculture and serves as the sovereign weather authority.

## Purpose
This adapter provides the formal government compliance layer on top of weather ingestion:
- Classification controls
- Arabic-primary alerts
- Data-sharing agreement tracking
- SLA/freshness monitoring

## Data Classification Requirements
All NDMC outputs are marked `SAUDI_GOVERNMENT_OFFICIAL` with handling guidance: official-use redistribution only with GCC approval.

## Arabic-Primary Alert Protocol
- `alert_ar` is mandatory and primary
- `alert_en` is secondary translation

## Military Weather Advisory Format
- Bilingual conditions (`conditions_ar`, `conditions_en`)
- Operational impact for flight/ground/UAV/maritime
- Sovereign authority and validity window

## Data-Sharing Agreement Structure
Agreement metadata tracks authority, ministry, covered data types, retention policy, and redistribution constraints.

## SLA Monitoring
`data_freshness_hours` maps to:
- compliant
- degraded
- non_compliant

## Relationship to Chunk 5 Adapter
- Chunk 5 `weather-saudi-ndmc`: parsing and ingestion mechanics
- Chunk 9 `sovereign-saudi-ndmc`: government compliance and sovereign governance

## Authentication
Primary production mode expects certificate-based auth/mTLS on government network.

## Smoke Test
```bash
python3 -m pytest -q packages/providers/sovereign-saudi-ndmc/tests/test_sovereign_ndmc_adapter.py
```
