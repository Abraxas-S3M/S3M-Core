# Sovereign Elm Runbook

## Platform Role
Elm provides Saudi government digital services relevant to S3M identity, vehicle, and records verification workflows.

## Authentication
Production access uses OAuth2 government credentials:
- `S3M_ELM_CLIENT_ID`
- `S3M_ELM_CLIENT_SECRET`

## Core Services
1. Identity verification (Phase 20 personnel readiness)
2. Vehicle registration lookup (Phase 17 asset/maintenance checks)
3. Government record search for enrichment

## Data Classification
All Elm integration data is treated as `SAUDI_GOVERNMENT_CONFIDENTIAL`.

## PII Handling Requirements
- Never log names, IDs, or addresses
- `sanitize_for_logging` must output only operational status fields
- Normalized identity output excludes personal names and identifiers

## Integration Points
- Phase 20 PersonnelRegistry for identity confirmation
- Phase 17 AssetRegistry for vehicle ownership type checks
- Intelligence enrichment workflows for controlled record lookups

## Air-Gapped Behavior
Adapters return fixture-based redacted responses for disconnected validation.

## Smoke Test
```bash
python3 -m pytest -q packages/providers/sovereign-elm/tests/test_elm_adapter.py
```
