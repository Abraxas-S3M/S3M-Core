# Google Earth Engine Provider Runbook

## Registration and Credentials
1. Enable Earth Engine at `https://earthengine.google.com/`.
2. Create service account key.
3. Set `S3M_GEE_SERVICE_ACCOUNT_KEY_PATH`.

## Key Collections
- `COPERNICUS/S1_GRD`
- `COPERNICUS/S2_SR_HARMONIZED`
- `NASA/VIIRS/002/VNP46A2`
- `MODIS/061/MOD11A1`
- `JRC/GSW1_4/GlobalSurfaceWater`
- `USGS/SRTMGL1_003`
- `LANDSAT/LC09/C02/T1_L2`

## Tactical Workflows
- Baseline-vs-current change detection for buildup/damage cues.
- Nighttime lights for military activity and grid disruption analysis.
- SRTM terrain profiles for navigation constraints.

## Air-Gapped Operations
GEE compute requires internet. For disconnected sites:
1. Export GeoTIFF/CSV/JSON on connected machine.
2. Transfer exports by approved USB.
3. Place in `data/integrations/geoint-gee/exports/`.
4. Adapter serves local exports and reports data age.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-gee/tests/ -v
```
