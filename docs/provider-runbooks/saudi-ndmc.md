# Saudi NDMC Provider Runbook

## Data Source Mode
Saudi NDMC adapter supports two modes:
1. Government API mode (if `S3M_NDMC_API_URL` and `S3M_NDMC_API_KEY` are set)
2. Default file-ingest mode from `data/integrations/weather-saudi-ndmc/incoming/`

## METAR Parsing Coverage
The adapter parses ICAO METAR strings including:
- Station/time group
- Wind direction/speed
- Gusts (`GxxKT`)
- Variable wind (`VRBxxKT`)
- Visibility
- Clouds
- Temperature/dewpoint
- QNH pressure

## Saudi Airport Set
12 stations are predefined (OERK, OEJN, OEDF, OETB, OEAB, OEMA, OEGN, OEGS, OEJB, OENR, OEKK, OEYN).

## Dust Phenomena Codes
- HZ: haze (light)
- DU / BLDU: dust / blowing dust (moderate)
- SA / BLSA: sand / blowing sand (heavy)
- DS: dust storm (storm)
- SS: sand storm (severe_storm)

## Alert Model
NDMC alerts are normalized with bilingual payloads:
- `description_en`
- `description_ar`

Severity follows NDMC style (yellow/orange/red/extreme).

## Sovereign Authority Rule
For Saudi operations, NDMC data/alerts take precedence over commercial weather providers
when building final operational assessments.

## Operational Threshold Context
NDMC extreme heat context uses 50C threshold (higher than many global civilian standards)
to match local Saudi climate realities and mission endurance constraints.

## Air-Gapped Notes
- METAR can be relayed via aviation/radio channels in disconnected operations.
- NDMC bulletin files can be synchronized via secure government networks.

## Smoke Test
```bash
python3 -m pytest packages/providers/weather-saudi-ndmc/tests/ -v
```
