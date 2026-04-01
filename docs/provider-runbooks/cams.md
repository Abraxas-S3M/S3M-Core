# CAMS Provider Runbook

## Registration and Credentials
1. Register with Copernicus ADS: `https://ads.atmosphere.copernicus.eu/`
2. Obtain key in `uid:key` format.
3. Set `S3M_CAMS_API_KEY`.

## Dust AOD Interpretation for Military Planning
- clear: < 0.1
- light_haze: 0.1-0.3
- moderate_dust: 0.3-0.5
- heavy_dust: 0.5-1.0
- sandstorm: 1.0-2.0
- severe_storm: > 2.0

## Visibility Estimation
Empirical relation used in adapter:
`visibility_km ~= 3.0 / (aod + 0.05)`, clamped to [0.1, 100.0].

## Saudi Dust Belt Context
Saudi Arabia lies in the Saharan-Arabian corridor. March-July Shamal winds routinely move
northwest-to-southeast dust plumes affecting aviation, ISR sensors, and exposed equipment.

## S3M Integration
- Phase 8 navigation: route around forecast dust fronts.
- Phase 15 SAR planning: prioritize windows before/after AOD peaks.
- Phase 17 maintenance: pre-stage filter replacements and optics covers.
- Tactical COP: explicit dust transport layer from CAMS model products.

## Cross-Provider Positioning
CAMS provides specialized atmospheric dust modeling; Open-Meteo provides broader weather context.
Both should be fused for final operations posture.

## Air-Gapped Operations
Store forecast extracts and regional dust snapshots for disconnected operations.

## Smoke Test
```bash
python3 -m pytest packages/providers/weather-cams/tests/ -v
```
