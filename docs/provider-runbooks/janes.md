# Janes Provider Runbook

## Contract and Access
- Janes defense intelligence access is contract-gated.
- Environment variable:
  - `S3M_JANES_API_KEY`

## Intelligence Domains
- Equipment and platform specifications.
- Country military profiles.
- Threat assessments and defense analysis.
- Order of battle (ORBAT) structures.

## S3M Integration Points
- Phase 16 ORBAT enrichment with authoritative structure references.
- Phase 17 AssetRegistry enrichment for equipment specs/performance.
- Phase 19 threat context from assessment and analysis feeds.

## Operational Workflow
1. Pull equipment/country/ORBAT/threat datasets.
2. Normalize to S3M-compatible enrichment structures.
3. Merge into mission intelligence products.

## Air-Gapped Operations
- Use fixture packs for repeatable training and validation.
- Keep periodic contract-approved snapshots for offline intelligence baselines.

## Smoke Test
```bash
python3 -m pytest packages/providers/intel-janes/tests/ -v
```
