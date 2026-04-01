# MarineTraffic Provider Runbook

## Registration and API Key Tiers
1. Register at MarineTraffic AIS API services.
2. Free trial tiers are typically near 100 calls/day; paid tiers scale to 1000+ calls/day.
3. Configure `S3M_MARINETRAFFIC_API_KEY` in deployment secrets.

## Authentication Pattern
- MarineTraffic embeds the API key in URL path segments.
- Base path used in S3M: `https://services.marinetraffic.com/api/exportvessels/v:8/{API_KEY}`.

## Endpoints Used in S3M
- **PS01** area vessel positions for Saudi maritime zones.
- **PS02** single-vessel position lookup.
- **PS07** extended area positions with ETA and next-port details.
- **VD01** vessel details (ownership, build year, DWT/GRT).
- **EV01** vessel events (arrivals/departures, area entry/exit, AIS gap start/end).
- **VH01** voyage history for historical movement analysis.

## Critical Unit Conversions
- `SPEED` is tenths of knots (`125 -> 12.5 kn`).
- `DRAUGHT` is tenths of meters (`200 -> 20.0 m`).

## Ship Type and Navigation Status Mapping
- MarineTraffic simplified type codes are mapped to tactical categories (`7 Cargo`, `8 Tanker`, `6 Passenger`).
- AIS navigation status includes mission-relevant states like underway, anchored, moored, and constrained-by-draught.

## Event Types for Dark Vessel Detection
- EV01 event codes consumed in S3M:
  - `1` port arrival
  - `2` port departure
  - `11` area entry
  - `12` area exit
  - `19` AIS gap start
  - `20` AIS gap end
- S3M pairs `19/20` to estimate dark intervals; gaps above one hour are flagged for escalation.

## Saudi Monitoring Zones (Phase 15 Aligned)
- persian_gulf
- red_sea_south
- strait_of_hormuz
- bab_el_mandeb
- jubail_coast
- gulf_of_aden

## S3M Integration Flow
- MarineTraffic live and cached tracks normalize to `NormalizedVesselTrack`.
- Maritime fusion pipeline enriches and deduplicates by MMSI.
- Phase 15 bridges:
  - `AISTracker` ingestion via CSV in `data/ais/`
  - `BorderSurveillanceEngine` alert feed for dark vessel indicators
  - `MaritimeFusionEngine` enrichment with provider tags/confidence

## Air-Gapped Operation Notes
- Export periodic zone snapshots/events on connected infrastructure.
- Transfer approved JSON snapshots via controlled removable media.
- In air-gapped mode S3M uses fixture/cache payloads only, with no external API calls.

## Smoke Test
```bash
python3 -m pytest packages/providers/maritime-marinetraffic/tests/ -v
```
