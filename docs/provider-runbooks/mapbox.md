# Mapbox Provider Runbook

## Registration and Token
1. Create an account at `https://www.mapbox.com/`.
2. Generate an access token with tile, geocoding, and directions scopes.
3. Set `S3M_MAPBOX_ACCESS_TOKEN` on the staging node before sync.

## Core Endpoints Used
- Vector tile: `/v4/mapbox.mapbox-streets-v8/{z}/{x}/{y}.mvt`
- Raster satellite: `/v4/mapbox.satellite-v9/{z}/{x}/{y}@2x.jpg`
- Static map: `/styles/v1/mapbox/satellite-streets-v12/static/...`
- Geocoding: `/geocoding/v5/mapbox.places/{query}.json`
- Routing: `/directions/v5/mapbox/driving/{origin};{dest}`
- Terrain tilequery: `/v4/mapbox.mapbox-terrain-v2/tilequery/{lon},{lat}.json`

## Style Profiles for Tactical Use
- `satellite_streets`: default COP base.
- `dark`: low-signature night operations.
- `outdoors`: contour-heavy ground maneuver planning.

## Offline Strategy (Air-Gapped)
1. Download region tile ranges while online.
2. Build MBTiles with `generate_offline_pack(region, max_zoom=14)`.
3. Copy MBTiles + tile cache to approved USB media.
4. Transfer to Jetson under `data/integrations/gis-mapbox/`.
5. Optional: serve with local tile server for dashboard nodes.

## Saudi Region Bounds
- `full_saudi`, `riyadh_metro`, `jeddah_metro`, `eastern_province`, `yemen_border`, `red_sea_coast`, `strait_of_hormuz`.

## Zoom-to-Resolution Guide
- z10: ~153 m/px
- z12: ~38 m/px
- z14: ~9.6 m/px

## Geocoding and Language
- Country filter: `SA,YE,OM,AE,KW,BH,QA`
- Language: `ar,en`
- Use bilingual output in COP search panels.

## S3M Integration
- Phase 6 dashboard COP base map and static mission briefs.
- Phase 8 navigation receives terrain query context and route fallback note.
- Air-gapped mode uses cache and MBTiles only.

## Smoke Test
```bash
python3 -m pytest packages/providers/gis-mapbox/tests -v
```
