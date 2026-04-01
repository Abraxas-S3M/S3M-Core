# SentinelHub Provider Runbook

## Registration and Credentials
1. Create an account at `https://apps.sentinel-hub.com`.
2. Create OAuth2 client credentials.
3. Set environment variables:
   - `S3M_SENTINELHUB_CLIENT_ID`
   - `S3M_SENTINELHUB_CLIENT_SECRET`

## Supported APIs in S3M
- Process API (`/api/v1/process`): rendered imagery tiles for COP overlays.
- Statistical API (`/api/v1/statistics`): temporal NDVI/NDWI analytic summaries.
- Catalog API (`/api/v1/catalog/1.0.0/search`): STAC scene discovery.

## Rate Limits
- Process: 2 req/s (120 rpm)
- Statistics: 2 req/s (120 rpm)
- Catalog: 5 req/s

## Evalscript Library
- `sar_ship_enhancement`
- `true_color_s2`
- `ndvi`
- `ndwi`
- `dust_aerosol`
- `thermal_hotspot`

## S3M Integration Notes
- Process API supports dashboard COP tile rendering.
- Statistics API supports trend and baseline widgets.
- Catalog API enables overlap deduplication with Copernicus.

## Air-Gapped Operations
- Cache processed tiles and JSON outputs on connected system.
- Transfer via approved removable media.
- Adapter serves fixture/cache outputs in `airgapped` mode.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-sentinelhub/tests/ -v
```
