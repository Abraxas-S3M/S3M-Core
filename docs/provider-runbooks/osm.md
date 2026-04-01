# OpenStreetMap / Overpass Provider Runbook

## Access Model
- No authentication is required for Overpass public endpoints.
- Recommended operational rate: `<=10 RPM` and `<=2` concurrent requests.

## Overpass Query Language
S3M issues bounded queries with `[out:json]` and tactical feature templates:
- Roads, buildings, military features, airports, ports
- Bridges/tunnels/power/fuel for logistics and route viability

## Offline PBF Strategy
1. Download Geofabrik extracts online:
   - `asia/gcc-states-latest.osm.pbf`
   - `asia/saudi-arabia-latest.osm.pbf`
2. Transfer PBF files to Jetson cache directory.
3. Optional: run local Overpass/tile stack from PBF for disconnected COP.
4. Alternative: pre-extract GeoJSON per AOI and store in extract cache.

## Bilingual Name Handling
- `name:en` preferred for English labels.
- `name:ar` preserved for Arabic labels.
- Fallback order: `name:en -> name -> None` and `name:ar -> None`.

## Tactical Context
- Phase 8 route planning uses normalized road classes and obstacles.
- Phase 6 COP overlays roads/buildings/military markers.
- Border monitoring can overlay fuel/power/tunnel chokepoints.

## Data Size Reference
- Saudi PBF is typically around 350 MB.
- GCC combined extract is approximately 700 MB.

## Air-Gapped Operation
- In `airgapped` mode, adapter serves from extract cache and local PBF metadata.
- No external API requests are made.

## Smoke Test
```bash
python3 -m pytest packages/providers/gis-osm/tests -v
```
