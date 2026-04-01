# NASA Earthdata / FIRMS Provider Runbook

## Registration and Credentials
1. Register MAP_KEY at `https://firms.modaps.eosdis.nasa.gov/api/area/`.
2. (Optional) Generate Earthdata token for CMR.
3. Set:
   - `S3M_NASA_FIRMS_MAP_KEY`
   - `S3M_NASA_EARTHDATA_TOKEN` (optional)

## Instruments
- `VIIRS_SNPP_NRT`
- `VIIRS_NOAA20_NRT`
- `MODIS_NRT`

## CSV Fields and Interpretation
- `bright_ti4`/`bright_ti5`: thermal brightness temperature in Kelvin.
- `frp`: Fire Radiative Power (MW), higher means larger/hotter event.
- `confidence`: low/nominal/high mapped to 0.3/0.7/0.95.

## Tactical Integration
- Cross-reference with strike claims for verification.
- Escalate sustained high-FRP clusters near industrial nodes.

## Air-Gapped Operations
- Import daily CSV snapshots and CMR JSON exports.
- Keep regional cache for continuity in denied networks.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-nasa-earthdata/tests/ -v
```
