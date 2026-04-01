# ICEYE Provider Runbook

## Access
- API key bearer access with contract credentials.
- Environment variable:
  - `S3M_ICEYE_API_KEY`

## Core Capabilities
- Rapid revisit X-band SAR collections.
- Built-in analytics for change detection and flood mapping.

## Tactical Analytics
- Change detection outputs structured change polygons and area estimates.
- Flood mapping provides immediate impact area estimation for crisis response.

## S3M Integration
- Complements Capella with additional constellation cadence.
- Supports Phase 19 monitoring workflows with SAR-driven deltas.

## Air-Gapped Operations
- Pre-stage catalog/tasking/analytics fixtures.
- Validate mission workflows without live credential dependency.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-iceye/tests/ -v
```
