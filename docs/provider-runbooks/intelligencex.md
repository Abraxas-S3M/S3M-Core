# Intelligence X Provider Runbook

## Provider Name and Category

- Provider: Intelligence X
- Category: OSINT Global Events

## Official API Documentation URL

- URL: https://intelx.io/tools?tab=api

## Authentication Setup

- Auth type: API key (`x-key` header)
- Setup procedure:
  1. Register Intelligence X account and generate API key.
  2. Add `S3M_INTELLIGENCEX_API_KEY` to the deployment secret store.
  3. Verify `validate_credentials()` passes in online mode.

## Required Environment Variables

- `S3M_INTELLIGENCEX_API_KEY`: Intelligence X API key.

## Rate Limits and Quotas

- Requests per minute: 3 (conservative for free tier)
- Daily/monthly quotas: free tier supports approximately 3 searches/hour and limited results.

## Supported Endpoints

- `POST /intelligent/search` - implemented
- `GET /intelligent/search/result?id=...` - implemented
- `POST /phonebook/search` - implemented

## Normalized Schemas Produced

- `NormalizedGlobalEvent`

## Search and Poll Workflow

1. Submit search term using `/intelligent/search`.
2. Poll `/intelligent/search/result` until `status == 2`.
3. Normalize records by bucket classification.

## Bucket Classification for S3M

- `pastes` -> `data_leak`
- `darknet` -> `darknet_activity`
- `whois*` -> `infrastructure_change`
- `dumpster`/`leaks` -> `data_breach`
- `news` -> `media_report`
- `web` -> `web_content`

## Saudi Infrastructure Monitoring Terms

- `aramco.com`
- `saudi.gov.sa`
- `ntc.sa`
- `sdaia.gov.sa`
- `moda.gov.sa`
- `stc.com.sa`
- `sabic.com`

## Leak Severity Classification

- Darknet + large file -> critical
- Paste + credential indicators -> high
- WHOIS changes -> medium
- News-only references -> low

## S3M Integration Notes

- Phase 13 SOC: leaked credential findings can trigger account hardening workflows.
- Phase 19 Intel: darknet monitoring contributes to strategic warning overlays.
- Phase 5 ThreatManager: infrastructure exposure findings enrich threat posture.

## Air-Gapped Operation Notes

- Export Intelligence X search snapshots regularly from connected environment.
- Place exported JSON fixtures in provider fixtures/cache paths.
- Adapter in air-gapped mode uses local fixtures only.

## Smoke Test Instructions

1. Run:
   ```bash
   python3 -m pytest packages/providers/osint-intelligencex/tests/ -v
   ```
2. Validate polling behavior with fixture status files.
3. Validate normalized bucket mapping and severity tags.
