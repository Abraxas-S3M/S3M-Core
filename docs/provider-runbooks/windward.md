# Windward Maritime AI Provider Runbook

## Registration and Credentials
1. Obtain Windward API subscription.
2. Configure `S3M_WINDWARD_API_KEY`.

## Authentication
- Header: `Authorization: apikey <key>`.

## Risk Scoring Methodology in S3M
- Windward scores map to S3M thresholds:
  - critical >= 80
  - high >= 60
  - medium >= 30
  - low < 30
- Dark-activity indicator score above 50 sets `is_dark=True` in normalized risk tracks.

## Indicator Types Tracked
- sanctions_proximity
- dark_activity
- sts_transfer
- flag_hopping
- identity_manipulation
- route_deviation
- port_risk
- cargo_risk

## Ownership Chain Analysis
- S3M parses beneficial owner, registered owner, operator, and flag history.
- Ownership chain supports sanctions and deceptive shipping investigations.

## S3M Integration
- Enriches Phase 15 BorderSurveillanceEngine alerts with risk context.
- Confirms dark-vessel suspicion with AI behavior analytics.
- Feeds maritime threat signals toward ThreatManager workflows.

## Saudi High-Risk Focus Zones
- bab_el_mandeb
- strait_of_hormuz
- gulf_of_aden

## Air-Gapped Notes
- In disconnected deployments, use vetted exported risk snapshots.
- AIRGAPPED mode avoids all external API calls.

## Smoke Test
```bash
python3 -m pytest packages/providers/maritime-windward/tests/ -v
```
