# Media Cloud Provider Runbook

## Provider Name and Category

- Provider: Media Cloud API v2
- Category: OSINT Global Events

## Official API Documentation URL

- URL: `https://api.mediacloud.org/api-docs`

## Registration and Authentication Setup

1. Create a Media Cloud account at `https://mediacloud.org`.
2. Generate an API key in your account settings.
3. Set `S3M_MEDIACLOUD_API_KEY` in the runtime environment.
4. For disconnected workflows, export approved JSON snapshots into provider fixtures.

## Required Environment Variables

- `S3M_MEDIACLOUD_API_KEY`

## Rate Limits and Quotas

- Requests per minute: 40 RPM
- Rows per request: up to 1000 (`max_rows`)
- Tactical recommendation: schedule query bursts around mission windows to reduce narrative blind spots.

## Implemented Endpoints

- `GET /stories_public/list`
  - Story search with date filtering and row limits.
- `GET /stories_public/count`
  - Time-series story counts (`split=true`, `split_period=day`) for surge detection.
- `GET /wc/list`
  - Word frequency extraction for dominant narrative terms.

## Solr Query Syntax and Collections

- Query language: Solr-like syntax (`AND`, `OR`, field filters, date range filters).
- Arabic collection tag used by S3M: `34412282`.
- S3M Arabic-vs-English comparison:
  - Arabic side: `media_sets_id:34412282`
  - English side: `language:en`
  - Coverage ratio far from `1.0` indicates asymmetric resonance or potential information operations.

## Narrative Surge Detection Methodology

- Pipeline computes a 7-day moving average baseline.
- Surge condition: daily count exceeds `3.0x` recent average.
- Output includes:
  - `date`
  - `count`
  - `average`
  - `multiplier`
  - `query`
- Tactical context: abrupt surges can indicate coordinated messaging campaigns before kinetic escalation.

## Normalized Schemas Produced

- `NormalizedGlobalEvent`
  - `event_type="media_report"`
  - `confidence=0.4`
  - tags include outlet name, language, and word-count bucket
- Trend utilities output normalized daily change percentages and surge flags.

## S3M Integration Notes

- Phase 19 `BriefingGenerator`:
  - Adds media landscape section (dominant narratives, trend shifts, top words).
- Phase 19 `CrisisTracker`:
  - Narrative surge events can trigger crisis escalation checks.
- Phase 11 `GeopoliticalModule`:
  - Arabic/English coverage imbalance is used as an info-ops indicator.

## Air-Gapped Operation Notes

- Mirror story list, count time-series, and word frequency JSON payloads into:
  - `packages/providers/osint-mediacloud/fixtures/`
  - `packages/providers/osint_mediacloud/fixtures/`
- Adapter runs fully in `airgapped` mode using fixture data only.
- No external API calls are required for tests.

## Smoke Test Instructions

```bash
python3 -m pytest packages/providers/osint-mediacloud/tests/ -v
```
